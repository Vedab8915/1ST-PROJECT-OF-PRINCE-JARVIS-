"""Small, local-only pairing server used by the Remote Control settings tab."""

from __future__ import annotations

import asyncio
import json
import secrets
import shutil
import socket
import time
import re
from pathlib import Path
from typing import Callable

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse


_PAGE = """<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>
<title>JARVIS Remote</title><style>body{margin:0;background:#061017;color:#dff8ff;font:16px system-ui;padding:24px;max-width:620px}input,button{box-sizing:border-box;width:100%;margin:8px 0;padding:14px;border-radius:8px;border:1px solid #24849c;background:#0d1c25;color:inherit}button{background:#00b8dd;color:#001117;font-weight:bold}#state{color:#8bf5ab}</style>
<h1>JARVIS Remote</h1><p id=state>Connecting…</p><input id=key inputmode=numeric maxlength=6 placeholder='6-digit pairing key'><button id=pair>PAIR</button><section id=controls hidden><input id=command placeholder='Type a command for JARVIS'><button id=send>SEND COMMAND</button></section>
<script>let ws;const q=new URLSearchParams(location.search).get('key');if(q)key.value=q;function connect(){ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws?key='+encodeURIComponent(key.value));ws.onopen=()=>{state.textContent='Connected';controls.hidden=false};ws.onclose=()=>{state.textContent='Pairing failed or disconnected';controls.hidden=true};ws.onmessage=e=>{try{let m=JSON.parse(e.data);if(m.type==='status')state.textContent='JARVIS: '+m.state}catch(_){}}}pair.onclick=connect;send.onclick=()=>{let text=command.value.trim();if(text&&ws&&ws.readyState===1){ws.send(JSON.stringify({type:'command',text}));command.value=''}};command.onkeydown=e=>{if(e.key==='Enter')send.click()};</script>"""


class DashboardServer:
    """Serve a LAN dashboard and bridge its commands to the live session."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host, self.port = host, port
        self._key = ""
        self._key_expires = 0.0
        self._clients: set[WebSocket] = set()
        self._connect_callback: Callable[[], object] | None = None
        self._command_queue: asyncio.Queue[str] = asyncio.Queue()
        self._phone_audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self._public_url: str | None = None
        self._tunnel_error = "Cloudflare Tunnel is not installed; using local Wi-Fi link."
        self._tunnel_process: asyncio.subprocess.Process | None = None
        self.app = FastAPI()
        self.app.get("/")(self._home)
        self.app.websocket("/ws")(self._socket)

    def set_connect_callback(self, callback: Callable[[], object]) -> None:
        self._connect_callback = callback

    def new_key(self) -> str:
        self._key = f"{secrets.randbelow(1_000_000):06d}"
        self._key_expires = time.time() + 600
        return self._key

    def get_url(self) -> str:
        # A Quick Tunnel is HTTPS and works from mobile data or any other
        # network.  Fall back to the LAN only while it is unavailable.
        return self._public_url or f"http://{self._lan_ip()}:{self.port}"

    def get_manual_url(self) -> str:
        return self.get_url()

    def tunnel_status(self) -> str:
        return "Public HTTPS link ready." if self._public_url else self._tunnel_error

    @staticmethod
    def _lan_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    async def _home(self) -> HTMLResponse:
        return HTMLResponse(_PAGE)

    def _valid_key(self, key: str) -> bool:
        return bool(self._key) and time.time() < self._key_expires and secrets.compare_digest(key, self._key)

    async def _socket(self, websocket: WebSocket) -> None:
        if not self._valid_key(websocket.query_params.get("key", "")):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        self._clients.add(websocket)
        callback = self._connect_callback
        if callback:
            result = callback()
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]
        try:
            while True:
                message = json.loads(await websocket.receive_text())
                if message.get("type") == "command":
                    text = str(message.get("text", "")).strip()
                    if text:
                        await self._command_queue.put(text)
        except (WebSocketDisconnect, ValueError):
            pass
        finally:
            self._clients.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        payload = json.dumps(message)
        await self._send_all(payload)

    async def broadcast_audio(self, _audio: bytes) -> None:
        # Text commands are the supported remote-control path.  Keep this hook
        # for the live audio relay without pushing large PCM payloads to phones.
        return

    async def _send_all(self, payload: str) -> None:
        for client in list(self._clients):
            try:
                await client.send_text(payload)
            except Exception:
                self._clients.discard(client)

    async def serve(self) -> None:
        # cloudflared's Quick Tunnel needs no account or router port-forwarding.
        # It is optional so the dashboard remains usable on a LAN without it.
        asyncio.create_task(self._start_tunnel())
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()

    async def _start_tunnel(self) -> None:
        bundled = Path(__file__).with_name("cloudflared.exe")
        executable = str(bundled) if bundled.is_file() else shutil.which("cloudflared")
        if not executable:
            return
        try:
            self._tunnel_error = "Starting secure public link…"
            self._tunnel_process = await asyncio.create_subprocess_exec(
                executable, "tunnel", "--url", f"http://127.0.0.1:{self.port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert self._tunnel_process.stdout is not None
            while True:
                line = await self._tunnel_process.stdout.readline()
                if not line:
                    break
                match = re.search(r"https://[-a-z0-9]+\.trycloudflare\.com", line.decode(errors="replace"), re.I)
                if match:
                    self._public_url = match.group(0)
                    self._tunnel_error = ""
                    print(f"[Dashboard] Public remote link ready: {self._public_url}")
                    return
            self._tunnel_error = "Cloudflare Tunnel stopped; using local Wi-Fi link."
        except Exception as exc:
            self._tunnel_error = f"Public tunnel failed ({exc}); using local Wi-Fi link."
            print(f"[Dashboard] {self._tunnel_error}")
