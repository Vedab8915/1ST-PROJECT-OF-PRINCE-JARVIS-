"""On-demand, system-wide hand gesture controls."""
from __future__ import annotations

import json
import os
import platform
import threading
import time
import urllib.request
from pathlib import Path

PLUGIN = {
    "name": "hand_gestures",
    "description": (
        "Only start when the user explicitly asks; stop when asked. While active: "
        "either pointing index moves the system-wide cursor; folding the right "
        "index left-clicks and folding the left index right-clicks; one-hand "
        "pinch-hold/move/release drags and drops; two pinched hands moving inward "
        "zoom out and spreading outward zooms in; open palm stops JARVIS speech; "
        "clenching a fist after an open palm minimizes all windows; held thumbs-up "
        "confirms with Enter and held thumbs-down ignores with Escape; two-finger "
        "swipes right/left change track and vertical movement scrolls; L shape "
        "takes a screenshot. Camera closes when stopped or if the service fails."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "operation": {
                "type": "STRING",
                "enum": ["start", "stop", "status"],
                "description": "Start gesture mode, stop it and release the camera, or check its status.",
            }
        },
        "required": ["operation"],
    },
}

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
_ROOT = Path(__file__).resolve().parent.parent
_MODEL_PATH = _ROOT / "config" / "hand_landmarker.task"
_STOP = threading.Event()
_LOCK = threading.RLock()
_THREAD: threading.Thread | None = None
_INTERRUPT = None
_NOTIFY = None


def configure_runtime(interrupt=None, notifier=None) -> None:
    """Connect the plugin to JARVIS's safe, existing UI callbacks."""
    global _INTERRUPT, _NOTIFY
    _INTERRUPT, _NOTIFY = interrupt, notifier


def _notify(message: str) -> None:
    if _NOTIFY:
        try:
            _NOTIFY(message)
        except Exception:
            pass


def _ensure_model() -> Path:
    if _STOP.is_set():
        raise RuntimeError("Gesture mode was stopped before the camera opened.")
    if _MODEL_PATH.is_file() and _MODEL_PATH.stat().st_size > 1_000_000:
        return _MODEL_PATH
    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _MODEL_PATH.with_suffix(".download")
    request = urllib.request.Request(_MODEL_URL, headers={"User-Agent": "JARVIS-HandGestures/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=40) as response, temp_path.open("wb") as out:
            while True:
                if _STOP.is_set():
                    raise RuntimeError("Gesture mode stopped while loading the hand model.")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        if temp_path.stat().st_size <= 1_000_000:
            raise RuntimeError("Downloaded hand tracking model is incomplete.")
        os.replace(temp_path, _MODEL_PATH)
        return _MODEL_PATH
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _load_camera_index() -> int:
    try:
        cfg_path = _ROOT / "config" / "api_keys.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return max(0, int(cfg.get("camera_index", 0)))
    except (OSError, ValueError, TypeError):
        return 0


def _hand_data(result) -> dict[str, dict]:
    found = {}
    for i, landmarks in enumerate(result.hand_landmarks):
        try:
            side = result.handedness[i][0].category_name.title()
        except (IndexError, AttributeError):
            side = "Right" if i == 0 else "Left"
        if side not in ("Left", "Right"):
            side = "Right" if i == 0 else "Left"
        points = [(float(p.x), float(p.y)) for p in landmarks]
        pose = _pose(points)
        palm = points[9]
        pinch = _distance(points[4], points[8]) / max(_distance(points[0], points[9]), 0.05)
        found[side] = {"points": points, "pose": pose, "palm": palm, "pinch": pinch}
    return found


def _distance(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _pose(p):
    """Classify basic poses from normalized hand landmarks."""
    # For a raised hand, a fingertip above its PIP joint means extended.
    extended = [p[tip][1] < p[pip][1] - 0.025
                for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18))]
    thumb_extended = _distance(p[4], p[2]) > _distance(p[3], p[2]) * 1.35
    thumb_up = p[4][1] < p[3][1] - 0.04
    thumb_down = p[4][1] > p[3][1] + 0.05
    index, middle, ring, pinky = extended
    if all(extended) and _distance(p[4], p[5]) > 0.10:
        return "OPEN"
    if index and thumb_extended and not middle and not ring and not pinky:
        return "L_SHAPE"
    if thumb_up and not any(extended):
        return "THUMB_UP"
    if thumb_down and not any(extended):
        return "THUMB_DOWN"
    if index and not middle and not ring and not pinky:
        return "POINT"
    if index and middle and not ring and not pinky:
        return "TWO"
    if not any(extended):
        return "FIST"
    return "OTHER"


class _GestureController:
    def __init__(self, pyautogui, stop_event: threading.Event):
        self.pg = pyautogui
        self.stop = stop_event
        self.screen_w, self.screen_h = pyautogui.size()
        self.last_cursor = None
        self.last_pose: dict[str, str] = {}
        self.last_action = 0.0
        self.pose_since: dict[str, float] = {}
        self.last_motion: dict[str, tuple[float, float, float]] = {}
        self.zoom_anchor = None
        self.dragging = False
        self.minimize_latched = False
        self._last_scroll = 0.0

    def _action_ready(self, gap=0.65) -> bool:
        now = time.monotonic()
        if now - self.last_action < gap:
            return False
        self.last_action = now
        return True

    def _cursor(self, point):
        # Keep a 5% edge margin so small camera jitters do not pin the pointer.
        x = (min(0.95, max(0.05, point[0])) - 0.05) / 0.90 * self.screen_w
        y = (min(0.95, max(0.05, point[1])) - 0.05) / 0.90 * self.screen_h
        if self.last_cursor:
            x = self.last_cursor[0] * 0.72 + x * 0.28
            y = self.last_cursor[1] * 0.72 + y * 0.28
        self.last_cursor = (x, y)
        self.pg.moveTo(int(x), int(y), duration=0)

    def _zoom(self, inward: bool):
        modifier = "command" if platform.system() == "Darwin" else "ctrl"
        self.pg.keyDown(modifier)
        try:
            self.pg.scroll(-3 if inward else 3)
        finally:
            self.pg.keyUp(modifier)
        _notify("Gesture: zoomed out." if inward else "Gesture: zoomed in.")

    def _minimize_all(self):
        system = platform.system()
        if system == "Darwin":
            self.pg.hotkey("command", "option", "m")
        elif system == "Windows":
            self.pg.hotkey("win", "m")
        else:
            self.pg.hotkey("win", "d")
        _notify("Gesture: minimized all windows.")

    def _screenshot(self):
        folder = _ROOT / "screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"gesture_{time.strftime('%Y%m%d_%H%M%S')}.png"
        self.pg.screenshot().save(path)
        _notify(f"Gesture: screenshot saved to {path}.")

    def process(self, hands: dict[str, dict], now: float):
        if not hands:
            self.zoom_anchor = None
            self.minimize_latched = False
            if self.dragging:
                self.pg.mouseUp(button="left")
                self.dragging = False
            self.last_pose.clear()
            self.pose_since.clear()
            self.last_motion.clear()
            return

        # Pointing with either index finger controls the global desktop pointer.
        pointer = hands.get("Right") if hands.get("Right", {}).get("pose") == "POINT" else None
        pointer = pointer or next((h for h in hands.values() if h["pose"] == "POINT"), None)
        if pointer:
            self._cursor(pointer["points"][8])

        # Two pinched hands together mean zoom. A single pinched hand means drag.
        pinch_limit = 0.50 if self.dragging else 0.34
        pinched = [h for h in hands.values() if h["pinch"] < pinch_limit]
        if len(pinched) >= 2:
            if self.dragging:
                self.pg.mouseUp(button="left")
                self.dragging = False
            separation = abs(pinched[0]["palm"][0] - pinched[1]["palm"][0])
            if self.zoom_anchor is None:
                self.zoom_anchor = separation
            elif separation < self.zoom_anchor - 0.075 and self._action_ready(0.8):
                self._zoom(inward=True)
                self.zoom_anchor = separation
            elif separation > self.zoom_anchor + 0.075 and self._action_ready(0.8):
                self._zoom(inward=False)
                self.zoom_anchor = separation
        else:
            self.zoom_anchor = None
            if pinched:
                hand = pinched[0]
                self._cursor(((hand["points"][4][0] + hand["points"][8][0]) / 2,
                              (hand["points"][4][1] + hand["points"][8][1]) / 2))
                if not self.dragging:
                    self.pg.mouseDown(button="left")
                    self.dragging = True
            elif self.dragging:
                self.pg.mouseUp(button="left")
                self.dragging = False

        for side, hand in hands.items():
            pose = hand["pose"]
            previous = self.last_pose.get(side)
            since = self.pose_since.setdefault(side, now)

            if hand["pinch"] < 0.34:
                self.last_pose[side] = "PINCH"
                self.pose_since[side] = now
                self.last_motion.pop(side, None)
                continue

            if pose == "OPEN" and now - since >= 0.45 and self._action_ready():
                if _INTERRUPT:
                    _INTERRUPT()
                _notify("Gesture: stopped JARVIS speech.")
                self.pose_since[side] = now + 10
            elif pose == "FIST" and previous == "OPEN" and self._action_ready():
                self._minimize_all()
            elif pose == "FIST" and previous == "POINT" and self._action_ready(0.25):
                # Fold right index = left click; fold left index = right click.
                button = "left" if side == "Right" else "right"
                self.pg.click(button=button)
                _notify(f"Gesture: {button}-click.")
            elif pose == "THUMB_UP" and now - since >= 0.65 and self._action_ready():
                self.pg.press("enter")
                _notify("Gesture: confirmed.")
                self.pose_since[side] = now + 10
            elif pose == "THUMB_DOWN" and now - since >= 0.65 and self._action_ready():
                self.pg.press("esc")
                _notify("Gesture: ignored.")
                self.pose_since[side] = now + 10
            elif pose == "TWO":
                old = self.last_motion.get(side)
                x, y = hand["palm"]
                if old:
                    ox, oy, ot = old
                    dx, dy = x - ox, y - oy
                    if now - ot < 0.7 and abs(dx) > 0.20 and abs(dx) > abs(dy) * 1.2 and self._action_ready():
                        self.pg.press("nexttrack" if dx > 0 else "prevtrack")
                        _notify("Gesture: next track." if dx > 0 else "Gesture: previous track.")
                        self.last_motion.pop(side, None)
                    elif abs(dy) > 0.035 and now - self._last_scroll > 0.08:
                        self.pg.scroll(1 if dy < 0 else -1)
                        self._last_scroll = now
                        self.last_motion[side] = (x, y, now)
                    elif now - ot > 0.7:
                        self.last_motion[side] = (x, y, now)
                else:
                    self.last_motion[side] = (x, y, now)
            else:
                self.last_motion.pop(side, None)

            if pose == "L_SHAPE" and previous != "L_SHAPE" and self._action_ready():
                self._screenshot()

            if pose != previous:
                self.pose_since[side] = now
            self.last_pose[side] = pose

    def release(self):
        if self.dragging:
            try:
                self.pg.mouseUp(button="left")
            except Exception:
                pass
            self.dragging = False
        try:
            self.pg.keyUp("ctrl")
            self.pg.keyUp("command")
        except Exception:
            pass


def _gesture_worker():
    cap = None
    landmarker = None
    controller = None
    try:
        import cv2
        import mediapipe as mp
        import pyautogui

        try:
            from mediapipe.tasks import BaseOptions
            from mediapipe.tasks.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
        except ImportError:
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

        _notify("Loading hand tracking model; the camera will open for gesture mode only.")
        model = _ensure_model()
        if _STOP.is_set():
            return
        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.60,
            min_tracking_confidence=0.60,
        )
        landmarker = HandLandmarker.create_from_options(options)

        cam_index = _load_camera_index()
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        cap = cv2.VideoCapture(cam_index, backend)
        if not cap.isOpened() and cam_index != 0:
            cap.release()
            cap = cv2.VideoCapture(0, backend)
        if not cap.isOpened():
            raise RuntimeError("Could not open the configured camera.")
        if _STOP.is_set():
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.01
        controller = _GestureController(pyautogui, _STOP)
        _notify("Hand gesture mode is ON. Camera is active; say 'stop gestures' to close it.")

        started = time.monotonic()
        while not _STOP.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.02)
                continue
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp = int((time.monotonic() - started) * 1000)
            result = landmarker.detect_for_video(image, timestamp)
            controller.process(_hand_data(result), time.monotonic())
            time.sleep(0.005)
    except Exception as exc:
        _notify(f"Hand gesture mode stopped: {exc}")
    finally:
        _STOP.set()
        if controller is not None:
            controller.release()
        if landmarker is not None:
            try:
                landmarker.close()
            except Exception:
                pass
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        _notify("Hand gesture mode is OFF. Camera released.")


def run(parameters: dict, **_kwargs) -> str:
    global _THREAD
    operation = str((parameters or {}).get("operation", "")).lower().strip()
    if operation == "start":
        with _LOCK:
            if _THREAD is not None and _THREAD.is_alive():
                return "Hand gesture mode is already active."
            _STOP.clear()
            _THREAD = threading.Thread(target=_gesture_worker, name="jarvis-hand-gestures", daemon=True)
            _THREAD.start()
        return "Hand gesture mode starting. The camera opens only for this mode."
    if operation == "stop":
        _STOP.set()
        thread = _THREAD
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        return "Hand gesture mode stopped; camera released."
    if operation == "status":
        return "Hand gesture mode is active." if _THREAD and _THREAD.is_alive() else "Hand gesture mode is off."
    return "Choose operation: start, stop, or status."
