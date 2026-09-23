"""Safe app discovery and user-confirmed Microsoft Store installation."""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
import urllib.parse
import webbrowser


def _run_winget(args: list[str], timeout: int = 45) -> tuple[int, str]:
    exe = shutil.which("winget")
    if not exe:
        return 127, "Windows Package Manager (winget) is not installed or not on PATH."
    try:
        p = subprocess.run(
            [exe, *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            shell=False,
        )
        return p.returncode, (p.stdout + "\n" + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "winget timed out while contacting the Store."
    except Exception as exc:
        return 1, f"Could not run winget: {exc}"


def _open_store_search(app_name: str) -> bool:
    uri = "ms-windows-store://search/?query=" + urllib.parse.quote(app_name)
    try:
        return bool(webbrowser.open(uri))
    except Exception:
        return False


def _open_edge_search(app_name: str) -> bool:
    url = "https://www.google.com/search?q=" + urllib.parse.quote(
        f"{app_name} official developer download"
    )
    if platform.system() == "Windows":
        candidates = [
            shutil.which("msedge"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for edge in candidates:
            if edge:
                try:
                    subprocess.Popen([edge, url], shell=False)
                    return True
                except Exception:
                    continue
        return False
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def app_download(parameters: dict, player=None) -> str:
    p = parameters or {}
    operation = str(p.get("operation", "search")).strip().lower()
    app_name = str(p.get("app_name", "")).strip()
    store_id = str(p.get("store_id", "")).strip()

    if operation not in {"search", "install", "external_search"}:
        return "Choose search, install, or external_search."
    if operation == "install":
        if platform.system() != "Windows":
            return "Microsoft Store installation is supported only on Windows."
        # Microsoft Store IDs contain letters and digits. Refuse free-form names,
        # URLs, and shell syntax: installs must target an exact Store catalog ID.
        if not re.fullmatch(r"[A-Za-z0-9]{8,20}", store_id):
            return "I need the exact Microsoft Store ID from the Store search before installing."
        code, details = _run_winget(
            ["show", "--id", store_id, "--source", "msstore", "--accept-source-agreements"]
        )
        if code != 0:
            return "I could not verify that exact ID in the Microsoft Store catalog. Nothing was installed.\n" + details[:900]
        if player:
            player.write_log(f"[app-download] Store metadata checked for {store_id}")
        from core import confirm as confirm_gate

        def _launch_install() -> str:
            exe = shutil.which("winget")
            if not exe:
                return "winget disappeared before installation; nothing was installed."
            # Keep winget interactive: don't accept package agreements, elevate,
            # suppress security UI, or run an installer silently.
            subprocess.Popen(
                [exe, "install", "--id", store_id, "--source", "msstore"],
                shell=False,
            )
            return "The Microsoft Store installation flow was started. Complete any Store prompts yourself."

        return confirm_gate.request(
            key=f"install-store-{store_id}",
            title="Install Microsoft Store app",
            detail=(
                f"Exact Store ID: {store_id}\n\n"
                "Check the Store listing price before approving. WinGet metadata does not reliably expose current pricing. "
                "Approve only if the listing is free and this is the app you requested. The Store remains interactive; "
                "JARVIS will not purchase, accept package agreements, bypass security, or elevate privileges."
            ),
            run=_launch_install,
        )

    if not app_name:
        return "Please specify the app name."
    if operation == "external_search":
        opened = _open_edge_search(app_name)
        return (
            "I opened a web search for the official developer download. Confirm the publisher and HTTPS domain yourself; "
            "I will not download or run an installer from an unverified result."
            if opened else "Could not open the browser. I cannot verify a safe official download source."
        )

    if platform.system() != "Windows":
        return "Microsoft Store search is supported only on Windows."
    code, output = _run_winget(
        ["search", "--name", app_name, "--source", "msstore", "--accept-source-agreements"]
    )
    if code != 0:
        return "Microsoft Store search failed. No download was started.\n" + output[:1200]
    opened = _open_store_search(app_name)
    msg = (
        "Microsoft Store search results (choose the exact legitimate publisher listing):\n"
        + output[:1800]
    )
    if opened:
        msg += "\nI also opened the Store listing search so you can verify publisher and price."
    msg += (
        "\nTell me the exact Store ID to proceed. If it is free, say to install it; "
        "the HUD will ask for a final confirmation. If it is paid or the publisher is unclear, I will stop."
    )
    if player:
        player.write_log(f"[app-download] Microsoft Store search: {app_name}")
    return msg


TOOL = {
    "name": "app_download",
    "description": (
        "Safe Windows app download flow. On 'download [app]', search Microsoft Store first and show exact matches; "
        "open Store search for the user to verify exact publisher and current price. Never infer current price from WinGet metadata. "
        "Only install an exact Store ID after the user has said the listing is free and asked to install; installation requires "
        "the separate human HUD confirmation. Keep winget interactive, never accept package agreements, elevate, silence, or "
        "bypass SmartScreen/antivirus/security. If absent, use external_search to open an Edge search for the official publisher; "
        "do not download/run external installers because this tool cannot independently verify the publisher domain. Stop if ambiguous/paid/unverified."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {"type": "STRING", "description": "search (default), install, or external_search"},
            "app_name": {"type": "STRING", "description": "Requested application name"},
            "store_id": {"type": "STRING", "description": "Exact Microsoft Store catalog ID shown by search"},
        },
        "required": [],
    },
    "handler": app_download,
}
