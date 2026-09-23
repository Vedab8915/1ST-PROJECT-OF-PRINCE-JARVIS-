import json
import subprocess
import sys
import re
import threading
import time
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

_CHAT_LOCK = threading.Lock()
_ACTIVE_CHAT: dict[str, str] = {}

_SENSITIVE_MESSAGE = re.compile(
    r"\b(password|passcode|otp|one.?time code|pin|bank|credit card|debit card|"
    r"payment|salary|medical|diagnos|prescription|home address|live location|"
    r"aadhaar|passport|social security|private photo|nude|resign|quit my job|"
    r"legal action|police|threat|blackmail)\b", re.IGNORECASE,
)


def _send(platform: str, receiver: str, message: str) -> str:
    return _resolve_platform(platform)(receiver, message)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _paste_text(text: str) -> None:
    _require_pyautogui()

    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")

    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)


def _clear_and_paste(text: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste_text(text)

def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = _get_os()

    try:
        if os_name == "windows":
            pyautogui.press("win")
            time.sleep(0.5)
            _paste_text(app_name)
            time.sleep(0.6)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True

        elif os_name == "mac":
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["open", "-a", f"{app_name}.app"],
                    capture_output=True, text=True, timeout=10,
                )
            time.sleep(2.5)
            return result.returncode == 0

        else: 
            launched = False
            for launcher in [
                ["gtk-launch", app_name.lower()],
                [app_name.lower()],
            ]:
                try:
                    subprocess.Popen(
                        launcher,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            time.sleep(2.5)
            return launched

    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open {app_name}: {e}")
        return False


def _open_browser_url(url: str) -> bool:
    import webbrowser
    try:
        webbrowser.open(url)
        time.sleep(4.0) 
        return True
    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open browser: {e}")
        return False

def _search_in_app(query: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    search_hotkey = ("command", "f") if os_name == "mac" else ("ctrl", "f")

    pyautogui.hotkey(*search_hotkey)
    time.sleep(0.5)
    _clear_and_paste(query)
    time.sleep(1.0)

def _desktop_send(app_name: str, receiver: str, message: str) -> str:
    if not _open_app(app_name):
        return f"Could not open {app_name}."

    time.sleep(1.0)
    _search_in_app(receiver)
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via {app_name}."

def _send_whatsapp(receiver: str, message: str) -> str:
    if not _open_app("WhatsApp"):
        return "Could not open WhatsApp."

    # Ctrl+N opens WhatsApp's new-chat/contact picker. Ctrl+F searches inside
    # the current conversation on many WhatsApp builds, so it often misses the
    # requested recipient entirely.
    os_name = _get_os()
    new_chat_hotkey = ("command", "n") if os_name == "mac" else ("ctrl", "n")
    pyautogui.hotkey(*new_chat_hotkey)
    time.sleep(0.7)
    _paste_text(receiver)
    time.sleep(1.0)
    pyautogui.press("enter")
    time.sleep(0.8)
    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via WhatsApp."

def _send_telegram(receiver: str, message: str) -> str:
    return _desktop_send("Telegram", receiver, message)

def _send_signal(receiver: str, message: str) -> str:
    return _desktop_send("Signal", receiver, message)


def _send_discord(receiver: str, message: str) -> str:
    return _desktop_send("Discord", receiver, message)


def _send_instagram(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.instagram.com/direct/new/"):
        return "Could not open Instagram in browser."

    _paste_text(receiver)
    time.sleep(1.5)

    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")   
    time.sleep(0.4)

    for _ in range(4):
        pyautogui.press("tab")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    return f"Message sent to {receiver} via Instagram."


def _send_messenger(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.messenger.com/"):
        return "Could not open Messenger in browser."


    _search_in_app(receiver)
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    return f"Message sent to {receiver} via Messenger."

_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"},              _send_whatsapp),
    ({"telegram", "tg"},                      _send_telegram),
    ({"instagram", "ig", "insta"},            _send_instagram),
    ({"signal"},                               _send_signal),
    ({"discord"},                              _send_discord),
    ({"messenger", "facebook", "fb"},         _send_messenger),
]


def _resolve_platform(platform_str: str):
    key = platform_str.lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    return lambda r, m: _desktop_send(platform_str.strip().title(), r, m)


def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params       = parameters or {}
    receiver     = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform     = params.get("platform", "whatsapp").strip()
    mode         = str(params.get("mode", "send")).strip().lower()

    if mode in {"stop", "pause"}:
        with _CHAT_LOCK:
            _ACTIVE_CHAT.clear()
        return "The active messaging context has been cleared. No further message was sent."

    if mode == "start_chat":
        if not receiver:
            return "Please specify the exact contact and platform before starting a chat."
        if not _PYAUTOGUI:
            return "PyAutoGUI is not installed — cannot control the desktop."
        intro = (
            "Hi, I'm Jarvis, Prince's AI assistant. Prince asked me to help with this conversation."
        )
        try:
            result = _send(platform, receiver, intro)
            if "sent" in result.lower():
                with _CHAT_LOCK:
                    _ACTIVE_CHAT.clear()
                    _ACTIVE_CHAT.update(receiver=receiver, platform=platform)
                return result + " I introduced myself as his AI assistant; tell me what to say next."
            return result
        except Exception as e:
            return f"Could not start the conversation: {e}"

    if not receiver:
        with _CHAT_LOCK:
            receiver = _ACTIVE_CHAT.get("receiver", "")
            platform = _ACTIVE_CHAT.get("platform", platform)
        if not receiver:
            return "Please specify a recipient, or start a conversation with an exact contact first."
    if not message_text:
        return "Please specify the message content."
    if not _PYAUTOGUI:
        return "PyAutoGUI is not installed — cannot control the desktop."

    preview = message_text[:50] + ("…" if len(message_text) > 50 else "")
    print(f"[SendMessage] 📨 {platform} → {receiver}: {preview}")
    if player:
        player.write_log(f"[msg] {platform} → {receiver}")

    if _SENSITIVE_MESSAGE.search(message_text):
        from core import confirm as confirm_gate
        return confirm_gate.request(
            key="send-sensitive-message",
            title=f"Send sensitive {platform} message",
            detail=f"To: {receiver}\nPlatform: {platform}\nMessage: {message_text[:240]}",
            run=lambda: _send(platform, receiver, message_text),
        )

    try:
        result  = _send(platform, receiver, message_text)
    except Exception as e:
        result = f"Could not send message: {e}"

    print(f"[SendMessage] {'✅' if 'sent' in result.lower() else '❌'} {result}")
    if player:
        player.write_log(f"[msg] {result}")

    return result


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "send_message",
    "description": "For a user-requested conversation, use mode=start_chat with the exact contact and platform first; JARVIS sends a clear one-time AI-assistant introduction, then waits for the user's next instruction. Use mode=send for the message the user specifically asked to send; after a chat starts, receiver may be omitted. Tanglish style must only be used when the user explicitly says to talk like them. Sensitive messages are held behind the human HUD confirmation. Use mode=pause or stop immediately when the user says pause/stop. This tool only sends; it cannot read or monitor inboxes or answer incoming calls. For WhatsApp, starts a new chat and searches the contact. Never use open_app alone for a request to message someone.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {
                "type": "STRING",
                "description": "send (default), start_chat (send the AI introduction before any user-directed conversation), pause, or stop",
            },
            "receiver": {
                "type": "STRING",
                "description": "Exact contact name the user specified"
            },
            "message_text": {
                "type": "STRING",
                "description": "The complete message text to send; preserve the user's meaning"
            },
            "platform": {
                "type": "STRING",
                "description": "The named messaging app (WhatsApp, Telegram, Instagram, Signal, Discord, Messenger); WhatsApp if unspecified"
            }
        },
        "required": [],
    },
    "handler": send_message,
}
