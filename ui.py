from __future__ import annotations

import json
import math
import os
import platform
import random
import re
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

from PyQt6.QtCore import (
    QEasingCurve, QEvent, QMimeData, QObject, QParallelAnimationGroup, QPointF,
    QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QIcon, QPen, QPixmap, QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QDialog,
    QInputDialog, QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSlider, QSplitter,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QProgressBar,
)
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

# ── P.R.I.N.C.E identity ─────────────────────────────────────────────────────
# One constant drives the window title, header badge and protocol display.
APP_VERSION  = "P.R.I.N.C.E"
APP_PROTOCOL = APP_VERSION.split()[-1]
UI_FONT      = "Orbitron"
BRANDING_FONT = "Bahnschrift"  # Cleaner title-style font for the P.R.I.N.C.E header branding

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"
APP_ICON   = CONFIG_DIR / "jarvis_icon.png"


# Local voice-unlock transcription helper.  The phrase itself is never persisted;
# only its salted PBKDF2 hash is stored by voice_lock.py.
_voice_stt = None
_voice_stt_lock = threading.Lock()
_voice_record_lock = threading.Lock()

def _record_voice_phrase(duration: float = 4.5) -> str:
    """Capture a short local microphone phrase and transcribe it with existing STT."""
    global _voice_stt
    with _voice_record_lock:
        import sounddevice as sd
        import numpy as np
        samples = int(16000 * max(2.0, min(8.0, float(duration))))
        audio = sd.rec(samples, samplerate=16000, channels=1, dtype="float32")
        sd.wait()
        arr = np.asarray(audio, dtype=np.float32).reshape(-1)
        if arr.size == 0 or float(np.sqrt(np.mean(arr * arr))) < 0.0025:
            return ""
        with _voice_stt_lock:
            if _voice_stt is None:
                from core.stt import WhisperSTT
                _voice_stt = WhisperSTT()
            text = _voice_stt.transcribe(arr)
        return str(text or "").strip()


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 820, 580
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


class C:
    BG        = "#00060a"
    PANEL     = "#010d14"
    PANEL2    = "#010f18"
    BORDER    = "#0d3347"
    BORDER_B  = "#1a5c7a"
    BORDER_A  = "#0f4060"
    PRI       = "#00d4ff"
    PRI_DIM   = "#007a99"
    PRI_GHO   = "#001f2e"
    ACC       = "#ff6b00"
    ACC2      = "#ffcc00"
    GREEN     = "#00ff88"
    GREEN_D   = "#00aa55"
    RED       = "#ff3355"
    MUTED_C   = "#ff3366"
    TEXT      = "#8ffcff"
    TEXT_DIM  = "#3a8a9a"
    TEXT_MED  = "#5ab8cc"
    WHITE     = "#d8f8ff"
    DARK      = "#000d14"
    BAR_BG    = "#011520"


# Keys tied to the accent colour — status colours (ACC, GREEN, RED…) stay fixed
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the whole teal-family palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    import colorsys

    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if not ss:
                continue
            s2 = ss
            for o, n in mapping.items():
                if o in s2:
                    s2 = s2.replace(o, n)
            if s2 != ss:
                w.setStyleSheet(s2)
                w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h); c.setAlpha(a); return c


class _EditableHeaderLabel(QLabel):
    double_clicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)


class _DraggableButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._drag_origin = None
        self._moved = False
        self.user_placed = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._moved = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            delta = event.globalPosition().toPoint() - self._drag_origin
            if delta.manhattanLength() > 4:
                self._moved = True
                self.user_placed = True
                parent = self.parentWidget()
                if parent is not None:
                    self.move(self.pos() + delta)
                self._drag_origin = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._moved:
            self._drag_origin = None
            event.accept()
            return
        self._drag_origin = None
        super().mouseReleaseEvent(event)


class _DraggableWaveform(QWidget):
    def __init__(self, hud: "HudCanvas", parent=None):
        super().__init__(parent)
        self._hud = hud
        self.user_placed = False
        self._drag_origin = None
        self._resize_origin = None
        self._start_geometry = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setMinimumSize(180, 52)

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        mid = 18
        amp = self._hud._amp_disp
        state = self._hud.state
        count = 36
        bar_width = max(3.0, (self.width() - 8) / count)
        for i in range(count):
            if self._hud.muted:
                height, color = 2.0, C.MUTED_C
            else:
                envelope = (1.0 - abs(i - (count - 1) / 2) / ((count - 1) / 2)) ** 0.7
                shimmer = 0.55 + 0.45 * math.sin(self._hud._tick * 0.18 + i * 0.7)
                idle = 2.0 + 1.5 * math.sin(self._hud._tick * 0.09 + i * 0.6)
                height = max(2.0, min(mid, idle + amp * 22.0 * envelope * shimmer))
                color = C.ACC if self._hud.speaking else (C.GREEN if state == "LISTENING" else C.PRI)
            p.setPen(QPen(qcol(color, 255 if amp > 0.05 else 180), 2))
            x = 4 + i * bar_width
            p.drawLine(QPointF(x, cy - height), QPointF(x, cy + height))
        p.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        margin = 22
        if event.position().x() >= self.width() - margin and event.position().y() >= self.height() - margin:
            self._resize_origin = event.globalPosition().toPoint()
            self._start_geometry = self.geometry()
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self._drag_origin = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        current = event.globalPosition().toPoint()
        if self._resize_origin is not None and self._start_geometry is not None:
            delta = current - self._resize_origin
            width = max(180, self._start_geometry.width() + delta.x())
            height = max(52, self._start_geometry.height() + delta.y())
            self.setFixedSize(width, height)
        elif self._drag_origin is not None:
            self.move(self.pos() + current - self._drag_origin)
            self._drag_origin = current
        event.accept()

    def mouseReleaseEvent(self, event):
        self.user_placed = True
        self._drag_origin = None
        self._resize_origin = None
        self._start_geometry = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        event.accept()


class _MovableOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user_placed = False
        self._drag_origin = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            current = event.globalPosition().toPoint()
            self.move(self.pos() + current - self._drag_origin)
            self._drag_origin = current
            self.user_placed = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_origin = None
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        event.accept()

# ── Windows GPU via NVML DLL (no subprocess, no console window) ──────────────
_nvml_lib: object = None   # cached ctypes DLL
_nvml_ok:  object = None   # None=untested, True=works, False=unavailable


def _nvml_gpu_windows() -> float:
    """Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return -1.0
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_ok = True
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)

        dev = ctypes.c_void_p()
        _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        util = _Util()
        _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
        _nvml_ok = True
        return float(util.gpu)
    except Exception:
        _nvml_ok = False
        return -1.0


class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        # Probe caches — GPU (NVML) and temperature (WMI) are the expensive
        # queries; initialise their handles once and reuse them instead of
        # rebuilding a connection on every poll.
        self._slow_tick = 0            # gpu/temp refreshed every 3rd cycle
        self._pynvml    = None         # cached pynvml module + device handle
        self._pynvml_h  = None
        self._pynvml_ok = None         # None=untested, False=unavailable here
        self._nv_unix   = None         # cached (lib, dev) for Linux/macOS NVML
        self._wmi_conn  = None         # cached WMI connection (creating one is slow)
        self._wmi_ok    = None         # None=untested, False=unavailable here
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(2.0)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        # GPU and temperature change slowly and are the most expensive probes
        # (NVML / WMI) — refresh them every 3rd cycle (~6 s) instead of every
        # cycle, reusing the previous reading in between.
        self._slow_tick = (self._slow_tick + 1) % 3
        if self._slow_tick == 1:
            gpu = self._get_gpu()
            tmp = self._get_temp()
        else:
            gpu = self.gpu
            tmp = self.tmp

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # pynvml — subprocess-free; initialise once and reuse the handle.
        # Re-initialising NVML on every poll is slow, so cache it and stop
        # retrying pynvml entirely once it proves unavailable here.
        if self._pynvml_ok is not False:
            try:
                if self._pynvml_h is None:
                    import pynvml  # type: ignore
                    pynvml.nvmlInit()
                    self._pynvml    = pynvml
                    self._pynvml_h  = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self._pynvml_ok = True
                return float(self._pynvml.nvmlDeviceGetUtilizationRates(self._pynvml_h).gpu)
            except Exception:
                self._pynvml_ok = False

        # Windows: nvml.dll via ctypes (already cached in _nvml_gpu_windows)
        if _OS == "Windows":
            return _nvml_gpu_windows()

        # Linux / macOS: libnvidia-ml shared lib via ctypes — init once, reuse
        try:
            import ctypes

            class _Util(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            if self._nv_unix is None:
                _lib = "libnvidia-ml.so.1" if _OS == "Linux" else "libnvidia-ml.dylib"
                nv = ctypes.CDLL(_lib)
                nv.nvmlInit_v2()
                dev = ctypes.c_void_p()
                nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
                self._nv_unix = (nv, dev)

            nv, dev = self._nv_unix
            u = _Util()
            nv.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            return float(u.gpu)
        except Exception:
            pass

        return -1.0   # N/A — zero subprocess on all platforms

    def _get_temp(self) -> float:
        # psutil — works on Linux; occasionally Windows with driver support
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                         "cpu-thermal", "zenpower", "it8688"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass

        # Windows: wmi module (pure Python COM, zero subprocess). Reuse a single
        # connection — building a fresh wmi.WMI() on every poll spins up a COM
        # connection each time and is very slow. Give up after one failure.
        if _OS == "Windows" and self._wmi_ok is not False:
            try:
                if self._wmi_conn is None:
                    import wmi  # type: ignore
                    self._wmi_conn = wmi.WMI(namespace="root/wmi")
                tz = self._wmi_conn.MSAcpi_ThermalZoneTemperature()
                if tz:
                    return (tz[0].CurrentTemperature / 10.0) - 273.15
            except Exception:
                self._wmi_ok   = False
                self._wmi_conn = None

        return -1.0   # N/A — zero subprocess on all platforms

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

class HudCanvas(QWidget):
    def __init__(self, face_path: str, assistant_name: str = "J.A.R.V.I.S", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALISING"
        self._assistant_name = assistant_name
        self.grid_brightness = 0.42

        self._tick       = 0
        self._anim_time  = 0.0
        self._anim_state = "INITIALISING"
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._halo       = 55.0
        self._tgt_halo   = 55.0
        self._last_t     = time.time()
        self._scan       = 0.0
        self._scan2      = 180.0
        self._rings      = [0.0, 120.0, 240.0]
        self._pulses: list[float] = [0.0, 50.0, 100.0]
        self._blink      = True
        self._blink_tick = 0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        # Rescaled-face cache: the smooth rescale is expensive, so we keep the
        # last result and only rebuild it when the (quantised) size changes.
        self._face_cache: QPixmap | None = None
        self._face_cache_sz = -1
        # Static grid-dot layer, pre-rendered once per size/theme into a pixmap
        # so paintEvent blits it in one call instead of thousands of drawPoint()s.
        self._grid_cache: QPixmap | None = None
        self._grid_key = None
        # Static vector caches: geometry is built only when the canvas size changes.
        self._tick_path = QPainterPath()
        self._crosshair_path = QPainterPath()
        self._ring_paths: list[QPainterPath] = []
        self._static_geom_key = None
        self._hud_font_small = QFont(UI_FONT, 11, QFont.Weight.Bold)
        self._hud_font_status = QFont(UI_FONT, 12, QFont.Weight.Bold)
        self._hud_pen_cache: dict[tuple, QPen] = {}
        self._load_face(face_path)

        # Live audio reactivity: _live_amp is written from the audio threads
        # (0.0–1.0), _amp_disp is the smoothed value the paint code reads.
        self._live_amp  = 0.0
        self._amp_disp  = 0.0
        self._base_scale = 1.0    # slow "breathing" target; amp is added per-frame
        self._base_halo  = 55.0

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.setTimerType(Qt.TimerType.PreciseTimer)
        self._tmr.start(16)

    def resizeEvent(self, event):
        self._grid_cache = None
        self._grid_key = None
        self._static_geom_key = None
        self._face_cache = None
        self._face_cache_sz = -1
        super().resizeEvent(event)

    def set_audio_level(self, level: float) -> None:
        """Thread-safe entry point for the audio threads. Stores the louder of
        the incoming level and the current value so brief gaps between chunks
        don't make the waveform stutter; _step() decays it back down."""
        try:
            lv = float(level)
        except (TypeError, ValueError):
            return
        if lv < 0.0:
            lv = 0.0
        elif lv > 1.0:
            lv = 1.0
        if lv > self._live_amp:
            self._live_amp = lv

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap(); px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None
        # New source image → drop the rescaled cache so it rebuilds on next paint.
        self._face_cache    = None
        self._face_cache_sz = -1

    def _make_grid(self, W: int, H: int) -> QPixmap:
        """Pre-render the static grid-dot background into a transparent pixmap so
        paintEvent can blit it once per frame instead of running a nested
        drawPoint() loop across the whole widget every 16 ms."""
        pm = QPixmap(max(1, W), max(1, H))
        pm.fill(Qt.GlobalColor.transparent)
        gp = QPainter(pm)
        alpha = max(20, min(220, int(self.grid_brightness * 255)))
        gp.setPen(QPen(qcol(C.PRI, alpha), 1))
        for x in range(0, W, 48):
            for y in range(0, H, 48):
                gp.drawPoint(x, y)
        gp.end()
        return pm

    def _rebuild_static_geometry(self, W: int, H: int) -> None:
        """Build geometry that does not change per animation frame."""
        fw = min(W, H)
        cx, cy = W / 2, H / 2

        tick = QPainterPath()
        t_out, t_in = fw * 0.247, fw * 0.229
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 6
            tick.moveTo(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad))
            tick.lineTo(cx + inn * math.cos(rad), cy - inn * math.sin(rad))
        self._tick_path = tick

        cross = QPainterPath()
        ch_r, gap_h = fw * 0.26, fw * 0.07
        cross.moveTo(cx - ch_r, cy); cross.lineTo(cx - gap_h, cy)
        cross.moveTo(cx + gap_h, cy); cross.lineTo(cx + ch_r, cy)
        cross.moveTo(cx, cy - ch_r); cross.lineTo(cx, cy - gap_h)
        cross.moveTo(cx, cy + gap_h); cross.lineTo(cx, cy + ch_r)
        self._crosshair_path = cross

        self._ring_paths = []
        for r_frac, _w_r, arc_l, gap in (
            (0.21, 3, 115, 78), (0.175, 2, 78, 55), (0.15, 1, 56, 40)
        ):
            r = fw * r_frac
            rect = QRectF(cx - r, cy - r, r * 2, r * 2)
            path = QPainterPath()
            angle = 0.0
            while angle < 360.0:
                path.arcMoveTo(rect, angle)
                path.arcTo(rect, angle, arc_l)
                angle += arc_l + gap
            self._ring_paths.append(path)

        self._static_geom_key = (W, H)

    def _step(self):
        self._tick += 1
        now = time.time()
        state = ("MUTED" if self.muted else
                 "SPEAKING" if self.speaking else (self.state or "").upper())
        if state != self._anim_state:
            self._anim_state = state
        thinking = state == "THINKING"
        processing = state == "PROCESSING"
        listening = state == "LISTENING"
        initializing = state in ("INITIALISING", "INITIALIZING")
        sleeping = state in ("SLEEPING", "STANDBY", "OFFLINE")
        active = thinking or processing or listening or initializing
        self._anim_time += 1.0 / 60.0

        # ── Live audio reactivity ────────────────────────────────────────────
        # Audio threads push peaks into _live_amp; decay it toward silence so
        # gaps between chunks fade out instead of freezing, then smooth it.
        self._live_amp *= 0.86
        self._amp_disp += (self._live_amp - self._amp_disp) * 0.45
        amp = self._amp_disp

        # Slow "breathing" base target (random shimmer), refreshed on a timer.
        if now - self._last_t > (0.12 if state == "SPEAKING" else (0.18 if active else 0.5)):
            if self.speaking:
                self._base_scale = 1.03
                self._base_halo  = 122.0
            elif processing:
                self._base_scale = 1.008
                self._base_halo  = 82.0
            elif thinking:
                self._base_scale = 1.0
                self._base_halo  = 64.0
            elif listening:
                self._base_scale = 1.006
                self._base_halo  = 72.0
            elif initializing:
                self._base_scale = 1.0
                self._base_halo  = 58.0
            elif sleeping:
                self._base_scale = 0.985
                self._base_halo  = 20.0
            elif self.muted:
                self._base_scale = random.uniform(0.998, 1.002)
                self._base_halo  = random.uniform(15, 28)
            else:
                self._base_scale = random.uniform(1.001, 1.008)
                self._base_halo  = random.uniform(48, 68)
            self._last_t = now

        # Every frame, the live audio level lifts the target on top of the base
        # — this is what makes the core visibly pulse to the actual voice.
        if state == "MUTED":
            self._tgt_scale, self._tgt_halo = self._base_scale, self._base_halo
        elif state == "SPEAKING":
            self._tgt_scale = self._base_scale + amp * 0.13
            self._tgt_halo  = self._base_halo  + amp * 95.0
        elif active:
            # Each mode has its own pulse rhythm: calm thought, quick work,
            # steady listening, and a short startup swell.
            rate = 1.0 if thinking else (3.2 if processing else (1.8 if listening else 2.5))
            depth = 0.010 if thinking else (0.022 if processing else (0.008 if listening else 0.035))
            phase = self._anim_time * rate
            self._tgt_scale = self._base_scale + math.sin(phase) * depth
            glow = 10.0 if thinking else (24.0 if processing else (18.0 if listening else 30.0))
            self._tgt_halo = self._base_halo + glow * (0.5 + 0.5 * math.sin(phase))
        elif sleeping:
            self._tgt_scale = self._base_scale + math.sin(self._anim_time * 0.45) * 0.004
            self._tgt_halo = self._base_halo + 4.0 * (0.5 + 0.5 * math.sin(self._anim_time * 0.45))
        else:
            self._tgt_scale = self._base_scale + amp * 0.06
            self._tgt_halo  = self._base_halo  + amp * 75.0

        sp = 0.38 if state == "SPEAKING" else (0.28 if active else (0.12 if sleeping or state == "MUTED" else 0.18))
        self._scale += (self._tgt_scale - self._scale) * sp
        self._halo  += (self._tgt_halo  - self._halo)  * sp

        # Rings/scanners spin faster while speaking, reacting to loudness.
        boost  = 1.0 + amp * 1.6
        speeds = {
            "INITIALISING": (1.8, -1.2, 2.4), "INITIALIZING": (1.8, -1.2, 2.4),
            "PROCESSING": (2.2, -1.6, 2.8), "THINKING": (0.18, -0.12, 0.28),
            "LISTENING": (0.8, -0.55, 1.15), "SPEAKING": (1.3, -0.9, 2.0),
            "SLEEPING": (0.08, -0.05, 0.10), "STANDBY": (0.08, -0.05, 0.10),
            "OFFLINE": (0.08, -0.05, 0.10), "MUTED": (0.0, 0.0, 0.0),
        }.get(state, (0.45, -0.3, 0.7))
        for i, spd in enumerate(speeds):
            self._rings[i] = (self._rings[i] + spd * boost) % 360

        scan_speed = {"INITIALISING": 2.6, "INITIALIZING": 2.6, "PROCESSING": 4.2,
                      "THINKING": 0.45, "LISTENING": 2.0, "SPEAKING": 3.0,
                      "SLEEPING": 0.16, "STANDBY": 0.16, "OFFLINE": 0.16,
                      "MUTED": 0.0}.get(state, 0.8)
        self._scan  = (self._scan  + scan_speed * boost) % 360
        reverse_scan = {"INITIALISING": -1.8, "INITIALIZING": -1.8, "PROCESSING": -3.1,
                        "THINKING": -0.3, "LISTENING": -1.25, "SPEAKING": -2.0,
                        "SLEEPING": -0.08, "STANDBY": -0.08, "OFFLINE": -0.08,
                        "MUTED": 0.0}.get(state, -0.5)
        self._scan2 = (self._scan2 + reverse_scan * boost) % 360

        fw  = min(self.width(), self.height())
        lim = fw * 0.48
        spd = {"INITIALISING": 3.0, "INITIALIZING": 3.0, "PROCESSING": 5.0,
               "THINKING": 0.9, "LISTENING": 2.6, "SPEAKING": 4.2,
               "SLEEPING": 0.45, "STANDBY": 0.45, "OFFLINE": 0.45,
               "MUTED": 0.0}.get(state, 1.5)
        self._pulses = [r + spd for r in self._pulses if r + spd < lim]
        pulse_chance = {"INITIALISING": 0.08, "INITIALIZING": 0.08, "PROCESSING": 0.09,
                        "THINKING": 0.012, "LISTENING": 0.045, "SPEAKING": 0.07,
                        "SLEEPING": 0.004, "STANDBY": 0.004, "OFFLINE": 0.004,
                        "MUTED": 0.0}.get(state, 0.02)
        if len(self._pulses) < 3 and random.random() < pulse_chance:
            self._pulses.append(0.0)

        if self.speaking and random.random() < 0.28:
            cx, cy = self.width() / 2, self.height() / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = fw * 0.28
            if len(self._particles) < 80:
                self._particles.append([
                    cx + math.cos(ang) * r_s, cy + math.sin(ang) * r_s,
                    math.cos(ang) * random.uniform(0.9, 2.4),
                    math.sin(ang) * random.uniform(0.9, 2.4) - 0.4, 1.0,
                ])
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.97, p[3]*0.97, p[4]-0.028]
            for p in self._particles if p[4] > 0
        ]

        self._blink_tick += 1
        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0
            _blinked = True
        else:
            _blinked = False

        # Keep the HUD at the same precise 60 Hz cadence in every state so
        # transitions and button-driven state changes never visibly hitch.
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():      # device not ready (e.g. 0-size during layout) — skip cleanly
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)
        if self._static_geom_key != (W, H):
            self._rebuild_static_geometry(W, H)

        # grid dots — blitted from a cached layer; rebuilt only when the size
        # or the theme's ghost colour changes (so live re-theming still works).
        _gkey = (W, H, C.PRI, self.grid_brightness)
        if self._grid_cache is None or self._grid_key != _gkey:
            self._grid_cache = self._make_grid(W, H)
            self._grid_key   = _gkey
        p.drawPixmap(0, 0, self._grid_cache)

        # Keep the reactor compact so the HUD has breathing room around it.
        r_face = fw * 0.17
        state = ("MUTED" if self.muted else
                 "SPEAKING" if self.speaking else (self.state or "").upper())
        state_color = {
            "INITIALISING": C.PRI, "INITIALIZING": C.PRI,
            "PROCESSING": C.ACC, "THINKING": C.ACC2,
            "LISTENING": C.GREEN, "SPEAKING": C.ACC,
            "MUTED": C.MUTED_C, "SLEEPING": C.TEXT_DIM,
            "STANDBY": C.TEXT_DIM, "OFFLINE": C.TEXT_DIM,
        }.get(state, C.PRI)

        # halo glow
        for i in range(10):
            r   = r_face * (1.8 - i * 0.08)
            frc = 1.0 - i / 10
            a   = max(0, min(255, int(self._halo * 0.085 * frc)))
            glow_col = state_color
            col = qcol(glow_col, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # pulse rings
        for pr in self._pulses:
            a   = max(0, int(230 * (1.0 - pr / (fw * 0.74))))
            ring_col = state_color
            col = qcol(ring_col, a)
            p.setPen(QPen(col, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # spinning arc rings — cached paths; only the transform changes per frame.
        p.setBrush(Qt.BrushStyle.NoBrush)
        ring_specs = ((3, 0.0), (2, 0.0), (1, 0.0))
        for idx, (width, _) in enumerate(ring_specs):
            a_val = max(0, min(255, int(self._halo * (1.0 - idx * 0.18))))
            ring_col = state_color if idx == 0 or state in ("THINKING", "PROCESSING") else C.PRI
            p.setPen(QPen(qcol(ring_col, a_val), width))
            p.save()
            p.translate(cx, cy)
            p.rotate(self._rings[idx])
            p.translate(-cx, -cy)
            p.drawPath(self._ring_paths[idx])
            p.restore()

        # scanners
        sr = fw * 0.24
        sa = min(255, int(self._halo * 1.5))
        ex = 75 if state == "SPEAKING" else (105 if state == "PROCESSING" else 34)
        scan_col = state_color
        p.setPen(QPen(qcol(scan_col, sa), 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(ex * 16))
        p.setPen(QPen(qcol(C.ACC, sa // 2), 1.5))
        p.drawArc(srect, int(self._scan2 * 16), int(ex * 16))

        # Give each state a different signature: a rotating boot dial, an
        # orbiting thought, a focused work sweep, a live voice meter, or radar.
        if state in ("INITIALISING", "INITIALIZING"):
            orbit_r = fw * 0.285
            for i in range(12):
                angle = math.radians(self._anim_time * 95 + i * 30)
                x = cx + math.cos(angle) * orbit_r
                y = cy + math.sin(angle) * orbit_r
                alpha = 70 + int(170 * ((i + int(self._anim_time * 8)) % 12) / 11)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(qcol(C.PRI, alpha)))
                p.drawEllipse(QPointF(x, y), 2.0 + (i % 3) * 0.5, 2.0 + (i % 3) * 0.5)
        elif state == "PROCESSING":
            loader_r = fw * 0.29
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(qcol(C.ACC, 42), 3))
            p.drawEllipse(QRectF(cx-loader_r, cy-loader_r, loader_r*2, loader_r*2))
            p.setPen(QPen(qcol(C.ACC, 230), 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(cx-loader_r, cy-loader_r, loader_r*2, loader_r*2),
                      int((-self._anim_time * 150) * 16), 92 * 16)
        elif state == "THINKING":
            orbit_r = fw * 0.255
            for i, color in enumerate((C.ACC2, C.PRI, C.ACC2)):
                angle = self._anim_time * 30 + i * (2 * math.pi / 3)
                point = QPointF(cx + math.cos(angle) * orbit_r,
                                cy + math.sin(angle) * orbit_r)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(qcol(color, 210)))
                p.drawEllipse(point, 3.2, 3.2)
        elif state == "LISTENING":
            angle = math.radians(self._anim_time * 95 - 90)
            outer = fw * 0.30
            p.setPen(QPen(qcol(C.GREEN, 180), 1.6))
            p.drawLine(QPointF(cx, cy), QPointF(cx + math.cos(angle)*outer,
                                                cy + math.sin(angle)*outer))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(qcol(C.GREEN, 100), 1))
            p.drawEllipse(QRectF(cx-outer, cy-outer, outer*2, outer*2))
        elif state == "SPEAKING":
            # A small equalizer follows the live audio level below the reactor.
            bar_y = cy + fw * 0.215
            for i in range(9):
                wave = 0.25 + 0.75 * abs(math.sin(self._anim_time * 8 + i * 0.72))
                height = 3 + (self._amp_disp * 25 + 5) * wave
                x = cx + (i - 4) * 8
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(qcol(C.ACC, 110 + int(wave * 130))))
                p.drawRoundedRect(QRectF(x-1.5, bar_y-height/2, 3, height), 1.5, 1.5)

        # tick marks — cached vector geometry.
        p.setPen(QPen(qcol(state_color, 170), 1))
        p.drawPath(self._tick_path)

        # crosshair — cached vector geometry.
        p.setPen(QPen(qcol(state_color, min(255, int(self._halo * 0.5))), 1))
        p.drawPath(self._crosshair_path)

        # face
        if self._face_px and self._assistant_name not in ("JARVIS", "J.A.R.V.I.S"):
            fsz = int(fw * 0.40 * self._scale)
            # Quantise the target size so the expensive smooth rescale only runs
            # when it visibly changes — not on every 1 px "breathing" step.
            q_sz = max(1, (fsz // 4) * 4)
            if self._face_cache is None or self._face_cache_sz != q_sz:
                self._face_cache = self._face_px.scaled(
                    q_sz, q_sz,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._face_cache_sz = q_sz
            scaled = self._face_cache
            p.drawPixmap(int(cx - scaled.width() / 2),
                         int(cy - scaled.height() / 2), scaled)
        else:
            # Keep the identity core outlined rather than a filled blue orb.
            core_r = int(fw * 0.06 * self._scale)
            core_col = state_color
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(qcol(core_col, min(255, int(self._halo * 2))), 2))
            p.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))
            p.setPen(QPen(qcol(C.WHITE, min(220, int(self._halo * 1.5))), 1))
            p.setFont(self._hud_font_small)
            p.drawText(QRectF(cx - 70, cy - 12, 140, 24),
                       Qt.AlignmentFlag.AlignCenter, self._assistant_name)

        # particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.PRI, a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 2.5, 2.5)

        # status text
        sy = cy + fw * 0.25
        if state == "MUTED":
            txt, col = "⊘  MUTED", qcol(C.MUTED_C)
        elif state == "SPEAKING":
            txt, col = "●  SPEAKING",  qcol(C.ACC)
        elif state == "THINKING":
            txt, col = f"◉  THINKING{'.' * (int(self._anim_time * 1.5) % 4)}", qcol(C.ACC2)
        elif state == "PROCESSING":
            txt, col = f"⟳  PROCESSING{'.' * (int(self._anim_time * 3) % 4)}", qcol(C.ACC)
        elif state == "LISTENING":
            txt, col = f"◖  LISTENING  ◗", qcol(C.GREEN)
        elif state in ("SLEEPING", "STANDBY", "OFFLINE"):
            txt, col = f"☾  {state}", qcol(C.TEXT_DIM)
        elif state in ("INITIALISING", "INITIALIZING"):
            txt, col = f"✦  INITIALISING{'.' * (int(self._anim_time * 2) % 4)}", qcol(C.PRI)
        else:
            txt, col = f"●  {state}", qcol(C.PRI)

        p.setPen(QPen(col, 1))
        p.setFont(self._hud_font_status)
        p.drawText(QRectF(0, sy, W, 26), Qt.AlignmentFlag.AlignCenter, txt)

        p.end()   # end deterministically so the backing store never flushes an active painter

class MetricBar(QWidget):

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0       # 0–100
        self._text  = "--"
        self.setFixedHeight(38)
        self.setMinimumWidth(80)

    def set_value(self, pct: float, text: str):
        v = max(0.0, min(100.0, pct))
        if v == self._value and text == self._text:
            return          # unchanged — skip the repaint
        self._value = v
        self._text  = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 4, 4)

        bar_h   = 4
        bar_y   = H - bar_h - 5
        bar_w   = W - 12
        bar_x   = 6
        fill_w  = int(bar_w * self._value / 100)

        p.setBrush(QBrush(qcol(C.BAR_BG)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        if self._value > 85:
            bar_col = qcol(C.RED)
        elif self._value > 65:
            bar_col = qcol(C.ACC)
        else:
            bar_col = qcol(self._color)

        if fill_w > 0:
            p.setBrush(QBrush(bar_col))
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        p.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(8, 5, 50, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_col if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(0, 4, W - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        p.end()

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        # Cap scrollback so an hours-long session can't grow the document
        # without bound — keeps memory flat and every insert cheap. Oldest
        # lines drop off the top automatically.
        self.document().setMaximumBlockCount(600)
        self.setFont(QFont(UI_FONT, 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._ai_name_lc = "jarvis"   # updated when assistant name changes
        self._chars_per_tick = 2
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        _ai_pfx = f"{self._ai_name_lc}:"
        if   tl.startswith("you:"):                              self._tag = "you"
        elif tl.startswith(_ai_pfx) or tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):                             self._tag = "file"
        elif "err" in tl:                                        self._tag = "err"
        else:                                                    self._tag = "sys"
        self._tmr.start(16)

    def _step(self):
        if self._pos < len(self._text):
            end = min(len(self._text), self._pos + self._chars_per_tick)
            chunk = self._text[self._pos:end]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(chunk, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos = end
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        # The marching-ants dashed border is only meaningful while the user is
        # hovering or dragging a file over the zone. When idle, skip the repaint
        # entirely instead of redrawing the whole zone 25×/s forever — that idle
        # repaint held the GIL and stole time from the audio/response threads.
        if not (self._hovering or self._drag_over):
            return
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._anim_tmr.start(40); self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._anim_tmr.stop(); self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        self._anim_tmr.stop()
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._anim_tmr.start(40); self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False
        if not self._drag_over:
            self._anim_tmr.stop()
        self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for JARVIS", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol("#001a24" if z._drag_over else ("#001218" if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

        p.end()

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont(UI_FONT, 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont(UI_FONT, 7))
        p.setPen(QPen(qcol("#1a4a5a"), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont(UI_FONT, 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont(UI_FONT, 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont(UI_FONT, 6))
        p.setPen(QPen(qcol("#1e5c6a"), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: rgba(0, 6, 10, 242);
                border: 1px solid {C.PRI};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 6)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel("◈  VISUAL INPUT")
        title.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setFont(QFont(UI_FONT, 8))
        close_btn.setStyleSheet(
            f"color: {C.TEXT_DIM}; background: transparent; border: none;"
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            max_w = self._W - 12
            scaled = px.scaled(
                max_w, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)   # auto-dismiss after 6 s


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(UI_FONT, font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure J.A.R.V.I.S. before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont(UI_FONT, 10))
        self._key_input.setFixedHeight(32)
        self._key_input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d12; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, QPushButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = QPushButton(label)
            btn.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = QPushButton("▸  INITIALISE SYSTEMS")
        init_btn.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        init_btn.setFixedHeight(36)
        init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        init_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; border: 1px solid {C.PRI};
            }}
        """)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,"#001a22"),"mac":(C.ACC2,"#1a1400"),"linux":(C.GREEN,"#001a0d")}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {fg}; color: {bg};
                        border: none; border-radius: 3px; font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #000d12; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
                """)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet() +
                f" QLineEdit {{ border: 1px solid {C.RED}; }}"
            )
            return
        self.done.emit(key, self._sel_os)


class HueWheel(QWidget):
    """
    Circular colour picker. The user drags the handle (small white circle)
    around the wheel to choose from ALL hues. The filled circle in the centre
    is a live preview of the selected colour.
    """

    hue_picked    = pyqtSignal(str)   # while dragging (live)
    hue_committed = pyqtSignal(str)   # when the handle is released

    _RING = 16   # ring thickness (px)

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue  = 0.53
        self._drag = False
        self.set_color(initial_hex)

    # ── API ──────────────────────────────────────────────────────────────────
    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c  = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()          # screen y goes down — flip to math axis
        ang = math.atan2(dy, dx)      # [-π, π], counter-clockwise
        return (ang / (2 * math.pi)) % 1.0

    # ── drawing ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = self._ring_rect()
        center = rect.center()

        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # centre preview circle
        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner   = rect.adjusted(30, 30, -30, -30)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)

        # draggable handle
        r   = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx  = center.x() + r * math.cos(ang)
        hy  = center.y() - r * math.sin(ang)
        p.setPen(QPen(QColor("#00060a"), 2))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(hx, hy), 7.5, 7.5)
        p.end()

    # ── fare ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._drag = True
        self._hue  = self._hue_from_pos(e.position())
        self.update()
        self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._hue = self._hue_from_pos(e.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())


class CustomizeOverlay(QWidget):
    """Floating overlay — change assistant name, user name, UI colour and voice."""

    saved = pyqtSignal(str, str, str, str)   # assistant_name, user_name, ui_color, voice
    _OW, _OH = 400, 588

    def __init__(self, assistant_name="JARVIS", user_name="",
                 ui_color=DEFAULT_UI_COLOR, voice="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont(UI_FONT, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; "
               f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        lay.addWidget(_lbl("⚙  CUSTOMISE ASSISTANT", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_lbl("ASSISTANT NAME", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._name_input = QLineEdit(assistant_name)
        self._name_input.setFont(QFont(UI_FONT, 10))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        lay.addWidget(_lbl("YOUR NAME  (leave blank for default sir / efendim)", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText("e.g.  Tony   (leave blank for auto)")
        self._user_input.setFont(QFont(UI_FONT, 10))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        # ── Assistant voice ──────────────────────────────────────────────────
        # Buttons use friendly labels; the internal Gemini voice ID stays hidden.
        from memory.config_manager import AVAILABLE_VOICES, DEFAULT_VOICE, get_voice_display_name
        lay.addSpacing(4)
        lay.addWidget(_lbl("ASSISTANT VOICE", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._sel_voice   = (voice or DEFAULT_VOICE)
        if self._sel_voice not in AVAILABLE_VOICES:
            self._sel_voice = DEFAULT_VOICE
        self._voice_btns: dict[str, QPushButton] = {}
        voice_row = QHBoxLayout(); voice_row.setSpacing(4)
        for _v in AVAILABLE_VOICES:
            b = QPushButton(get_voice_display_name(_v))
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=_v: self._on_voice_pick(name))
            self._voice_btns[_v] = b
            voice_row.addWidget(b)
        lay.addLayout(voice_row)
        self._refresh_voice_btns()

        # ── UI colour — colour wheel ─────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        clr_hdr.addWidget(_lbl("UI COLOUR  —  drag the handle", 8,
                               color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        clr_hdr.addStretch()
        df_btn = QPushButton("DEFAULT")
        df_btn.setFixedSize(64, 20)
        df_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — live preview; MainWindow wires it

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setPlaceholderText("#00d4ff   (custom hex colour)")
        self._hex_input.setFont(QFont(UI_FONT, 10))
        self._hex_input.setFixedHeight(28)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = QPushButton("▸  APPLY CHANGES")
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("CANCEL")
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(QFont(UI_FONT, 9))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── voice selection ──────────────────────────────────────────────────────
    def _on_voice_pick(self, name: str):
        self._sel_voice = name
        self._refresh_voice_btns()

    def _refresh_voice_btns(self):
        """Highlight the selected voice pill; dim the rest."""
        for name, b in self._voice_btns.items():
            on = (name == self._sel_voice)
            b.setChecked(on)
            if on:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 3px; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    # ── colour flow ──────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Updates the selected colour; hex box + wheel stay in sync, theme is live-previewed."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # While dragging: update the hex box, don't apply the theme yet
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Handle released → live-preview the whole interface
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # If a preview was applied, revert to the colour from launch
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "JARVIS"
        user = self._user_input.text().strip()
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR, self._sel_voice)
        self.hide()


class PluginManagerOverlay(QWidget):
    """Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles."""

    _OW = 420

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🧩  PLUGIN MANAGER")
        hdr.setFont(QFont(UI_FONT, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        if not plugins:
            empty = QLabel("No plugins found in /plugins.")
            empty.setFont(QFont(UI_FONT, 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(empty)

        for p in plugins:
            lay.addLayout(self._build_row(p))

        lay.addSpacing(4)
        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(30)
        close_btn.setFont(QFont(UI_FONT, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)
        self.adjustSize()

    def _build_row(self, p: dict) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)

        label_text = p["name"] if p["valid"] else f"{p['name']}  (⚠ {p['file']})"
        lbl = QLabel(label_text)
        lbl.setFont(QFont(UI_FONT, 8))
        lbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.TEXT_DIM}; background: transparent;")
        lbl.setToolTip(p["description"] if p["valid"] else p["error"])
        lbl.setWordWrap(False)
        row.addWidget(lbl, stretch=1)

        btn = QPushButton()
        btn.setFixedSize(72, 24)
        btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        if not p["valid"]:
            btn.setText("BROKEN")
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
            """)
        else:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_toggle(btn, p["enabled"])
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        row.addWidget(btn)
        return row

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText("ON")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            btn.setText("OFF")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)

    def _toggle(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)


class _HudOverlay(QWidget):
    """Base for the floating panels placed by hand over the HUD.

    They are children of the central widget but sit in no layout, so Qt never
    invalidates the region they occupy when they hide or shrink: the HUD keeps
    painting around them and their last frame stays on screen as a ghost. Any
    overlay positioned with _centre_overlay needs this."""

    def hideEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            # Repaint exactly what we were covering, before we stop covering it.
            p.update(self.geometry())
        super().hideEvent(e)

    def closeEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().closeEvent(e)


class ConfirmBanner(_HudOverlay):
    """The gate in front of an action that cannot be taken back.

    The old confirmation was a tool parameter the model filled in itself, which
    means it confirmed its own shutdown requests. This is the interface asking,
    and the answer travels from a human finger to core/confirm.py without the
    model in the loop. Nothing blocks while it is up: the assistant keeps
    talking, so this costs no latency — unlike the old gate, which spent two
    tool round trips on every power command."""

    answered = pyqtSignal(bool)
    _OW = 430

    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ConfirmBanner {{
                background: rgba(14, 3, 0, 250);
                border: 1px solid {C.ACC};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        hdr = QLabel("⚠  CONFIRM")
        hdr.setFont(QFont(UI_FONT, 11, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        lay.addWidget(hdr)

        ttl = QLabel(title)
        ttl.setWordWrap(True)
        ttl.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(ttl)

        if detail:
            dtl = QLabel(detail)
            dtl.setWordWrap(True)
            dtl.setFont(QFont(UI_FONT, 8))
            dtl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            lay.addWidget(dtl)

        row = QHBoxLayout(); row.setSpacing(8)

        yes = QPushButton("▸  CONFIRM")
        yes.setFixedHeight(32)
        yes.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.ACC};
                border: 1px solid {C.ACC}; border-radius: 3px; }}
            QPushButton:hover {{ background: rgba(255,107,0,40); }}
        """)
        yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(yes)

        no = QPushButton("CANCEL")
        no.setFixedHeight(32)
        no.setFont(QFont(UI_FONT, 9))
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        no.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(no)
        lay.addLayout(row)

        # Default focus on CANCEL: if someone hits Enter without reading, the
        # safe answer wins.
        no.setDefault(True)
        no.setFocus()


class AudioDeviceOverlay(_HudOverlay):
    """Choose which microphone JARVIS listens to and which speakers it uses.

    Both audio streams used to open with no `device=` at all, so they always
    took the OS default — which on Windows moves by itself the moment a headset
    is plugged in. 'JARVIS can't hear me' is usually 'JARVIS is listening to the
    webcam'."""

    picked = pyqtSignal()      # emitted after Apply, when something changed
    _OW = 460

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.audio_devices import list_devices, DEFAULT_LABEL
        from memory.config_manager import get_input_device, get_output_device

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AudioDeviceOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🎧  AUDIO DEVICES")
        hdr.setFont(QFont(UI_FONT, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        _combo_css = (
            f"QComboBox {{ background: #000d12; color: {C.TEXT}; "
            f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
            f"QComboBox:hover {{ border-color: {C.BORDER_B}; }}"
            f"QComboBox QAbstractItemView {{ background: #000d12; color: {C.TEXT}; "
            f"selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}"
        )

        def _row(label: str, kind: str, current: str) -> QComboBox:
            cap = QLabel(label)
            cap.setFont(QFont(UI_FONT, 8))
            cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(cap)

            box = QComboBox()
            box.setFont(QFont(UI_FONT, 9))
            box.setFixedHeight(30)
            box.setStyleSheet(_combo_css)
            # The list is served from a cache warmed on a background thread at
            # startup, so opening this panel never blocks the Qt thread on the
            # host audio API.
            box.addItem(DEFAULT_LABEL, "")
            for name in list_devices(kind):
                box.addItem(name, name)
            idx = box.findData(current) if current else 0
            box.setCurrentIndex(idx if idx >= 0 else 0)
            if current and idx < 0:
                # Saved device is not plugged in right now. Show it rather than
                # silently resetting the user's choice to default.
                box.addItem(f"{current}  (not connected)", current)
                box.setCurrentIndex(box.count() - 1)
            lay.addWidget(box)
            return box

        self._in_box  = _row("MICROPHONE — what JARVIS hears you with",
                             "input", get_input_device())
        lay.addSpacing(4)
        self._out_box = _row("SPEAKERS — what JARVIS talks through",
                             "output", get_output_device())

        note = QLabel("Applying reconnects the session. Your conversation is kept.")
        note.setWordWrap(True)
        note.setFont(QFont(UI_FONT, 7))
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addSpacing(6)
        lay.addWidget(note)

        row = QHBoxLayout(); row.setSpacing(8)
        ok = QPushButton("▸  APPLY")
        ok.setFixedHeight(32)
        ok.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        ok.clicked.connect(self._apply)
        row.addWidget(ok)

        cancel = QPushButton("CLOSE")
        cancel.setFixedHeight(32)
        cancel.setFont(QFont(UI_FONT, 9))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel.clicked.connect(self.hide)
        row.addWidget(cancel)
        lay.addLayout(row)

    def _apply(self):
        from memory.config_manager import (
            get_input_device, get_output_device,
            save_input_device, save_output_device,
        )
        new_in  = self._in_box.currentData()  or ""
        new_out = self._out_box.currentData() or ""
        changed = (new_in != get_input_device()) or (new_out != get_output_device())
        save_input_device(new_in)
        save_output_device(new_out)
        self.hide()
        # Only rebuild the session if something actually moved — a no-op Apply
        # should not cost a reconnect.
        if changed:
            self.picked.emit()


class MemoryOverlay(_HudOverlay):
    """Everything JARVIS has stored about you, and when it learned it.

    Memory used to be a 2200-character store that deleted its oldest entries
    when full and mentioned it only on stdout. The cap is gone; this panel is
    the other half of that change — a memory you cannot inspect is a memory you
    cannot trust, and 'delete' has to be something the person can do."""

    _OW = 520

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            MemoryOverlay {{
                background: rgba(0, 6, 10, 246);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(5)
        self._rebuild()

    def _clear_layout(self):
        """Take every item out of the layout and detach it from the widget tree
        in this call.

        deleteLater() on its own is not enough: it queues destruction for the
        next event-loop pass, and until then the old rows are still children of
        this widget and still paint — which is what drew half of the previous
        panel over the new one. setParent(None) removes them from the tree now;
        deleteLater() then frees them safely."""
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # hide() stops it painting in this frame; deleteLater() frees it
                # safely afterwards. setParent(None) would also stop the paint,
                # but it turns the widget into a top-level window for the moment
                # between the two calls, which is not something to leave lying
                # around inside a click handler.
                w.hide()
                w.deleteLater()
                continue
            sub = item.layout()
            if sub is not None:
                while sub.count():
                    si = sub.takeAt(0)
                    sw = si.widget()
                    if sw is not None:
                        sw.hide()
                        sw.deleteLater()
                sub.deleteLater()

    def _settle(self, before):
        """Size the panel to its content, re-centre it, and repaint what the old
        size covered.

        The re-size has to happen here rather than at the end of _rebuild
        because Qt has not polished the freshly-created children at that point,
        so the size hint it would read is the empty-layout one. Measured: a
        first adjustSize() returned 32 px for a panel whose content needed 155,
        and a second call — after the same widgets had been through the event
        loop — returned 155. So this runs twice: once now, once on the next
        turn, from _rebuild.

        The re-centre and the repaint are needed because the overlay is placed
        by hand and is in no layout: shrinking it leaves it off-centre and
        leaves its former pixels on screen, since nothing tells the parent that
        region changed. The repaint has to cover the union of the old and new
        rectangles."""
        self._lay.invalidate()
        self._lay.activate()
        self.updateGeometry()
        self.adjustSize()

        p = self.parentWidget()
        if p is None:
            self.update()
            return
        self.move(max(0, (p.width()  - self.width())  // 2),
                  max(0, (p.height() - self.height()) // 2))
        p.update(before.united(self.geometry()))
        self.update()

    def _rebuild(self):
        before = self.geometry()
        self._clear_layout()

        from memory.memory_manager import all_entries_for_ui

        hdr = QLabel("🧠  WHAT JARVIS REMEMBERS")
        hdr.setFont(QFont(UI_FONT, 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._lay.addWidget(hdr)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        self._lay.addWidget(sep)

        rows = all_entries_for_ui()

        cap = QLabel(f"{len(rows)} stored facts — newest first. "
                     f"Nothing here is sent anywhere; it lives in "
                     f"memory/long_term.json on this machine.")
        cap.setWordWrap(True)
        cap.setFont(QFont(UI_FONT, 7))
        cap.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._lay.addWidget(cap)

        if not rows:
            empty = QLabel("Nothing stored yet.")
            empty.setFont(QFont(UI_FONT, 9))
            empty.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            self._lay.addWidget(empty)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFixedHeight(min(420, 34 * len(rows) + 10))
            scroll.setStyleSheet(
                f"QScrollArea {{ border: 1px solid {C.BORDER}; border-radius: 3px; "
                f"background: transparent; }}"
            )
            inner = QWidget()
            ilay  = QVBoxLayout(inner)
            ilay.setContentsMargins(6, 6, 6, 6)
            ilay.setSpacing(3)

            for r in rows:
                line = QHBoxLayout(); line.setSpacing(6)
                txt = QLabel(f"<b>{r['key'].replace('_', ' ')}</b> "
                             f"<span style='color:{C.TEXT_MED}'>— {r['value']}</span>")
                txt.setWordWrap(True)
                txt.setFont(QFont(UI_FONT, 8))
                txt.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
                line.addWidget(txt, 1)

                meta = QLabel(f"{r['category'][:4]} · {r['updated'] or '—'}")
                meta.setFont(QFont(UI_FONT, 7))
                meta.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                line.addWidget(meta)

                rm = QPushButton("✕")
                rm.setFixedSize(20, 20)
                rm.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
                rm.setCursor(Qt.CursorShape.PointingHandCursor)
                rm.setToolTip("Forget this")
                rm.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
                """)
                rm.clicked.connect(
                    lambda _=False, c=r["category"], k=r["key"]: self._forget(c, k))
                line.addWidget(rm)

                holder = QWidget()
                holder.setLayout(line)
                ilay.addWidget(holder)

            ilay.addStretch()
            scroll.setWidget(inner)
            self._lay.addWidget(scroll)

        close = QPushButton("CLOSE")
        close.setFixedHeight(30)
        close.setFont(QFont(UI_FONT, 9))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close.clicked.connect(self.hide)
        self._lay.addWidget(close)

        self._settle(before)
        # …and again once Qt has polished the new children, because the size
        # hint is not final until then. Harmless when the first pass already
        # got it right: _settle is idempotent.
        QTimer.singleShot(0, lambda g=before: self._settle(g))

    def _forget(self, category: str, key: str):
        from memory.memory_manager import forget
        forget(key, category)
        # Rebuild on the NEXT event-loop turn, not inside this click handler.
        # The rebuild destroys the very ✕ button that emitted this signal, and
        # Qt is entitled to touch the sender after a slot returns; tearing it
        # down mid-emission is how a widget ends up half-alive on screen.
        QTimer.singleShot(0, self._rebuild)


class ClipboardPanel(QWidget):
    """Floating panel shown when text is copied — offers quick Jarvis actions."""

    action_requested = pyqtSignal(str)
    _W, _H = 326, 112

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipboardPanel {{
                background: rgba(0, 8, 14, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)
        self._clip_text = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 7)
        lay.setSpacing(4)

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        icon_lbl = QLabel("◈  CLIPBOARD DETECTED")
        icon_lbl.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        hdr.addWidget(icon_lbl); hdr.addStretch()
        x_btn = QPushButton("✕")
        x_btn.setFixedSize(16, 16)
        x_btn.setFont(QFont(UI_FONT, 8))
        x_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        x_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        x_btn.clicked.connect(self.hide)
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        self._preview = QLabel()
        self._preview.setFont(QFont(UI_FONT, 8))
        self._preview.setStyleSheet(f"""
            color: {C.TEXT}; background: {C.PANEL2};
            border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 6px;
        """)
        self._preview.setWordWrap(False)
        self._preview.setFixedHeight(28)
        lay.addWidget(self._preview)

        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        _bs = (f"QPushButton {{ background: {C.PANEL2}; color: {C.TEXT_MED}; "
               f"border: 1px solid {C.BORDER}; border-radius: 2px; }}"
               f"QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}")
        for label, cmd_fmt in [
            ("TRANSLATE", "Translate this text to English: {text}"),
            ("SUMMARISE", "Summarise this: {text}"),
            ("EXPLAIN",   "Explain this: {text}"),
            ("FIX",       "Fix grammar and spelling: {text}"),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(22)
            b.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_bs)
            b.clicked.connect(lambda _, c=cmd_fmt: self._trigger(c))
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)
        self.hide()

    def _trigger(self, cmd_fmt: str):
        if self._clip_text:
            self.action_requested.emit(cmd_fmt.format(text=self._clip_text[:800]))
        self.hide()

    def show_clipboard(self, text: str):
        self._clip_text = text
        preview = text[:58].replace('\n', ' ')
        if len(text) > 58:
            preview += "…"
        self._preview.setText(f'"{preview}"')
        self.show(); self.raise_()
        self._dismiss_timer.start(8000)


class PluginSettingsOverlay(QWidget):
    """Floating overlay — renders per-plugin settings forms.

    Fully generic: it iterates the settings schemas a plugin declared via its
    PLUGIN_SETTINGS constant (delivered by PluginRegistry.settings_schemas) and
    builds a form for each. It knows NOTHING about any specific plugin, so the
    core stays clean and plugins remain pure drop-in — install a plugin that
    declares fields (e.g. the 3D-printer suite) and its section appears here;
    install none and this panel simply says there's nothing to configure.
    """

    _test_done = pyqtSignal(str, bool, str)   # namespace, ok, message
    _OW = 460

    def __init__(self, sections: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginSettingsOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self._sections = sections or []
        self._widgets: dict[tuple, object] = {}    # (namespace, key) -> input widget
        self._types:   dict[tuple, str]    = {}     # (namespace, key) -> field type
        self._status_labels: dict[str, QLabel] = {} # namespace -> status QLabel
        self._test_done.connect(self._on_test_done)

        self._fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
                    f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(8)

        root.addWidget(self._lbl("⚙  PLUGIN SETTINGS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        root.addWidget(sep)

        if not self._sections:
            root.addWidget(self._lbl(
                "No configurable plugins are installed.\nDrop a plugin that needs "
                "settings (like the 3D-printer suite) into the plugins folder and "
                "it will show up here.", 9, color=C.TEXT_DIM))
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; }")
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            form = QVBoxLayout(inner)
            form.setContentsMargins(0, 0, 6, 0)
            form.setSpacing(6)
            for sec in self._sections:
                self._build_section(form, sec)
            form.addStretch(1)
            scroll.setWidget(inner)
            root.addWidget(scroll, 1)

        # ── bottom buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        if self._sections:
            save_btn = QPushButton("▸  SAVE")
            save_btn.setFixedHeight(34)
            save_btn.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
            """)
            save_btn.clicked.connect(self._save_all)
            btn_row.addWidget(save_btn)

        close_btn = QPushButton("CLOSE")
        close_btn.setFixedHeight(34)
        close_btn.setFont(QFont(UI_FONT, 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _lbl(self, txt, fs=9, bold=False, color=C.PRI,
             align=Qt.AlignmentFlag.AlignLeft):
        w = QLabel(txt); w.setAlignment(align); w.setWordWrap(True)
        w.setFont(QFont(UI_FONT, fs,
                        QFont.Weight.Bold if bold else QFont.Weight.Normal))
        w.setStyleSheet(f"color: {color}; background: transparent;")
        return w

    def _build_section(self, form: QVBoxLayout, sec: dict):
        ns     = sec.get("namespace") or sec.get("plugin") or "plugin"
        title  = sec.get("title") or ns
        fields = sec.get("fields") or []
        values = sec.get("values") or {}

        form.addSpacing(4)
        form.addWidget(self._lbl(title, 10, True, C.PRI))

        for field in fields:
            if not isinstance(field, dict) or not field.get("key"):
                continue
            key   = field["key"]
            ftype = (field.get("type") or "text").lower()
            label = field.get("label") or key
            default = field.get("default")
            stored  = values.get(key, default)

            form.addWidget(self._lbl(label.upper(), 8, color=C.TEXT_DIM))

            if ftype == "choice":
                w = QComboBox()
                w.addItems([str(o) for o in field.get("options", [])])
                w.setFont(QFont(UI_FONT, 9))
                w.setFixedHeight(30)
                w.setStyleSheet(
                    f"QComboBox {{ background: #000d12; color: {C.TEXT}; "
                    
                    f"QComboBox QAbstractItemView {{ background: #000d12; color: {C.TEXT}; "
                    f"selection-background-color: {C.PRI_GHO}; }}")
                if stored is not None:
                    w.setCurrentText(str(stored))
            elif ftype == "toggle":
                w = QPushButton()
                w.setCheckable(True)
                w.setChecked(bool(stored))
                w.setFixedHeight(28)
                w.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
                w.setCursor(Qt.CursorShape.PointingHandCursor)
                self._style_toggle(w)
                w.toggled.connect(lambda _=False, b=w: self._style_toggle(b))
            else:  # text / password
                w = QLineEdit("" if stored is None else str(stored))
                w.setFont(QFont(UI_FONT, 10))
                w.setFixedHeight(30)
                w.setStyleSheet(self._fs)
                if field.get("placeholder"):
                    w.setPlaceholderText(str(field["placeholder"]))
                if ftype == "password":
                    w.setEchoMode(QLineEdit.EchoMode.Password)

            self._widgets[(ns, key)] = w
            self._types[(ns, key)]   = ftype
            form.addWidget(w)

        # optional test/connect action button + status line
        action = sec.get("action")
        if isinstance(action, dict) and callable(action.get("run")):
            form.addSpacing(2)
            ab = QPushButton(str(action.get("label") or "TEST"))
            ab.setFixedHeight(30)
            ab.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            ab.setStyleSheet(f"""
                QPushButton {{ background: #00091a; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
            """)
            ab.clicked.connect(lambda _=False, n=ns: self._run_action(n))
            form.addWidget(ab)

        status = self._lbl("", 8, color=C.TEXT_DIM)
        self._status_labels[ns] = status
        form.addWidget(status)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C.BORDER}; margin: 4px 0;")
        form.addWidget(line)

    def _style_toggle(self, btn: QPushButton):
        on = btn.isChecked()
        btn.setText("ON" if on else "OFF")
        if on:
            btn.setStyleSheet(f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI}; "
                              f"border: 1px solid {C.PRI}; border-radius: 3px; }}")
        else:
            btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; "
                              f"border: 1px solid {C.BORDER}; border-radius: 3px; }}")

    # ── data ──────────────────────────────────────────────────────────────────
    def _gather(self, ns: str) -> dict:
        out = {}
        for (n, key), w in self._widgets.items():
            if n != ns:
                continue
            t = self._types.get((n, key), "text")
            if t == "choice":
                out[key] = w.currentText()
            elif t == "toggle":
                out[key] = w.isChecked()
            else:
                out[key] = w.text().strip()
        return out

    def _save_ns(self, ns: str):
        from memory.config_manager import save_plugin_config
        save_plugin_config(ns, self._gather(ns))

    def _save_all(self):
        for sec in self._sections:
            ns = sec.get("namespace") or sec.get("plugin")
            if ns:
                self._save_ns(ns)
                lbl = self._status_labels.get(ns)
                if lbl:
                    lbl.setText("Saved ✓")
                    lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")

    def _run_action(self, ns: str):
        sec = next((s for s in self._sections
                    if (s.get("namespace") or s.get("plugin")) == ns), None)
        if not sec:
            return
        run_fn = (sec.get("action") or {}).get("run")
        if not callable(run_fn):
            return
        self._save_ns(ns)                 # persist what the user typed before testing
        values = self._gather(ns)
        lbl = self._status_labels.get(ns)
        if lbl:
            lbl.setText("Testing…")
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")

        def worker():
            try:
                res = run_fn(values)
                if isinstance(res, tuple) and len(res) == 2:
                    ok, msg = bool(res[0]), str(res[1])
                else:
                    ok, msg = bool(res), str(res)
            except Exception as e:
                ok, msg = False, str(e)
            self._test_done.emit(ns, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ns: str, ok: bool, msg: str):
        lbl = self._status_labels.get(ns)
        if not lbl:
            return
        lbl.setText(msg)
        color = C.PRI if ok else "#ff6b6b"
        lbl.setStyleSheet(f"color: {color}; background: transparent;")


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback."""

    closed = pyqtSignal()

    _OW, _OH = 400, 465

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: rgba(0, 4, 12, 0.95);
                border: 1px solid {C.BORDER_B};
                border-radius: 14px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(5)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont(UI_FONT, fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        lay.addWidget(_lbl("◈  REMOTE ACCESS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep)

        # ── QR code ───────────────────────────────────────────────────────────
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(176, 176)
        self._qr_label.setStyleSheet(
            "background: white; border-radius: 10px; padding: 4px;"
        )
        qr_row = QHBoxLayout()
        qr_row.addStretch()
        qr_row.addWidget(self._qr_label)
        qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        lay.addWidget(_lbl("Scan with phone camera to connect instantly", 8, color=C.TEXT_DIM))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_lbl("Or enter manually:", 7, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))

        self._url_lbl = QLabel(self._manual_url)
        self._url_lbl.setFont(QFont(UI_FONT, 8))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._url_lbl)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont(UI_FONT, 28, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 10px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont(UI_FONT, 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._timer_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        new_btn = QPushButton("NEW KEY")
        new_btn.setFixedHeight(32)
        new_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = QPushButton("DISMISS")
        close_btn.setFixedHeight(32)
        close_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=5, border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(170, 170,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont(UI_FONT, 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 10px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont(UI_FONT, 7))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 10px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont(UI_FONT, 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            "color: #00ff88; background: #001a0d; border-radius: 10px;"
        )
        self._timer_lbl.setText("Phone connected — JARVIS ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class JarvisSettingsHub(_HudOverlay):
    """
    Unified Futuristic Cyberpunk / Iron Man Settings Command Center.
    Completely replaces legacy drawers and scattered overlay modals.
    Consolidates:
      • Identity, Persona & Holographic Theme
      • Audio Routing & Wake Word Engine
      • Neural Core System & API Authorization
      • Neural Memory Vault
      • Modular Extensions & Plugin Credentials
      • Mobile Telemetry & Remote QR Pairing
    """
    closed = pyqtSignal()
    _OW, _OH = 820, 580

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window.centralWidget())
        self._main = main_window
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("JarvisSettingsHub")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        self._active_tab_idx = 0
        self._tab_buttons: list[QPushButton] = []
        self._sel_voice = ""
        self._initial_color = DEFAULT_UI_COLOR
        self._sel_color = DEFAULT_UI_COLOR
        self._qr_timer = None
        self._expiry = 0
        self._key_lbl = None
        self._timer_lbl = None
        self._qr_label = None

        # Face Security state is deliberately session-only.  It is reset every
        # time the Settings hub is closed/reopened; the backend owns the PIN
        # hash, face database and biometric recognition logic.
        self._face_security_unlocked = False
        self._face_security_root = None
        self._face_locked_panel = None
        self._face_unlocked_panel = None
        self._face_pin_input = None
        self._face_pin_status = None
        self._face_list_lay = None
        self._face_auth_toggle = None

        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"""
            QWidget#JarvisSettingsHub {{
                background: rgba(0, 8, 14, 0.97);
                border: 1px solid {C.BORDER_B};
                border-radius: 12px;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: rgba(0, 5, 10, 0.5);
                width: 6px;
                border-radius: 3px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.PRI};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
                border: none;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(10)

        # ── Futuristic Top Header ───────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setContentsMargins(4, 2, 4, 4)
        hdr.setSpacing(10)

        icon_lbl = QLabel("◈")
        icon_lbl.setFont(QFont(UI_FONT, 14, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(1)
        title_lbl = QLabel("SYSTEM CONFIGURATION // COMMAND CENTER")
        title_lbl.setFont(QFont(UI_FONT, 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {C.WHITE}; background: transparent; letter-spacing: 1.5px;")
        title_vbox.addWidget(title_lbl)

        sub_lbl = QLabel(f"PROTOCOL: {APP_PROTOCOL}  ·  AI CORE ONLINE  ·  MARK-LIII")
        sub_lbl.setFont(QFont(UI_FONT, 7))
        sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        title_vbox.addWidget(sub_lbl)
        hdr.addLayout(title_vbox)

        hdr.addStretch()

        status_badge = QLabel("● ACTIVE")
        status_badge.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        status_badge.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(0, 255, 136, 0.08);
            border: 1px solid rgba(0, 255, 136, 0.4);
            border-radius: 10px;
            padding: 3px 10px;
        """)
        hdr.addWidget(status_badge)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setFont(QFont(UI_FONT, 11, QFont.Weight.Bold))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close Settings [Esc]")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 6px;
            }}
            QPushButton:hover {{
                color: {C.RED}; border-color: {C.RED}; background: rgba(255, 51, 85, 0.1);
            }}
        """)
        close_btn.clicked.connect(self.hide_hub)
        hdr.addWidget(close_btn)
        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 0 4px;")
        root.addWidget(sep)

        # ── Main Body: Left Sidebar + Right Stack ───────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        # Sidebar navigation rail
        sidebar = QWidget()
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet("background: transparent;")
        side_lay = QVBoxLayout(sidebar)
        side_lay.setContentsMargins(0, 4, 0, 4)
        side_lay.setSpacing(5)

        tabs_info = [
            ("🎛️  IDENTITY & THEME", "Identity, Voice & Holographic Appearance"),
            ("🎙️  AUDIO & VOICE",   "Hardware Routing & Wake Word Engine"),
            ("⚡  CORE SYSTEM",     "API Keys, Platform & Launch Settings"),
            ("🧠  NEURAL MEMORY",   "Long-Term Memory Inspection & Vault"),
            ("🧩  PLUGINS & EXT",   "Installed Add-ons & Device Credentials"),
            ("🔐  FACE SECURITY",   "PIN-protected face authentication & authorized faces"),
            ("📱  REMOTE ACCESS",   "Mobile Phone Pairing & Telemetry QR"),
            ("🔒  JARVIS LOCK SYSTEM", "Face, Master PIN & Voice Unlock Security"),
        ]

        self._tab_buttons = []
        for idx, (label, tooltip) in enumerate(tabs_info):
            btn = QPushButton(label)
            btn.setFixedHeight(40)
            btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.clicked.connect(lambda _, i=idx: self.set_tab(i))
            side_lay.addWidget(btn)
            self._tab_buttons.append(btn)

        side_lay.addStretch()

        # Mini info pill in sidebar bottom
        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        info_pill = QLabel(f"SYS.OS: {os_name}\nNET: ONLINE\nENC: AES-256")
        info_pill.setFont(QFont(UI_FONT, 7))
        info_pill.setStyleSheet(f"""
            color: {C.TEXT_DIM};
            background: rgba(0, 15, 25, 0.4);
            border: 1px solid {C.BORDER};
            border-radius: 6px;
            padding: 6px 8px;
        """)
        side_lay.addWidget(info_pill)
        body.addWidget(sidebar)

        # Right Stacked Widget
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        self._stack.addWidget(self._build_identity_tab())
        self._stack.addWidget(self._build_audio_tab())
        self._stack.addWidget(self._build_core_tab())
        self._stack.addWidget(self._build_memory_tab())
        self._stack.addWidget(self._build_plugins_tab())
        self._stack.addWidget(self._build_face_security_tab())
        self._stack.addWidget(self._build_remote_tab())
        self._stack.addWidget(self._build_lock_system_tab())

        body.addWidget(self._stack, stretch=1)
        root.addLayout(body, stretch=1)

        self._refresh_tab_styles()

    def _card_frame(self) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: rgba(1, 14, 22, 0.75);
                border: 1px solid {C.BORDER};
                border-radius: 8px;
            }}
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        return card, lay

    def _sec_label(self, text: str, size: int = 9) -> QLabel:
        l = QLabel(text)
        l.setFont(QFont(UI_FONT, size, QFont.Weight.Bold))
        l.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 0.5px;")
        return l

    def _dim_label(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setFont(QFont(UI_FONT, 7))
        l.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        return l

    # ── TAB 0: IDENTITY & THEME ───────────────────────────────────────────
    def _build_identity_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(10)

        cfg = _read_full_config()

        # 1. Persona Card
        card1, c1_lay = self._card_frame()
        c1_lay.addWidget(self._sec_label("◈  ASSISTANT IDENTITY & CALL-SIGN"))

        c1_lay.addWidget(self._dim_label("ASSISTANT NAME / CALL-SIGN"))
        self._name_input = QLineEdit(self._main._assistant_name)
        self._name_input.setFont(QFont(UI_FONT, 9))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(f"""
            QLineEdit {{ background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px; }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        c1_lay.addWidget(self._name_input)

        c1_lay.addWidget(self._dim_label("USER ADDRESS / TITLE (e.g. Tony, Commander, Sir)"))
        self._user_input = QLineEdit(cfg.get("user_name", ""))
        self._user_input.setPlaceholderText("e.g. Tony (leave blank for auto)")
        self._user_input.setFont(QFont(UI_FONT, 9))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(f"""
            QLineEdit {{ background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px; }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        c1_lay.addWidget(self._user_input)

        c1_lay.addWidget(self._dim_label("HUD BRAND SUBTITLE"))
        self._sub_input = QLineEdit(cfg.get("hud_subtitle", "") or self._main._sub_lbl.text())
        self._sub_input.setFont(QFont(UI_FONT, 9))
        self._sub_input.setFixedHeight(32)
        self._sub_input.setStyleSheet(f"""
            QLineEdit {{ background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px; }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        c1_lay.addWidget(self._sub_input)
        lay.addWidget(card1)

        # 2. Voice Matrix Card
        from memory.config_manager import (
            AVAILABLE_VOICES, DEFAULT_VOICE, get_voice, get_voice_display_name,
        )
        card2, c2_lay = self._card_frame()
        c2_lay.addWidget(self._sec_label("◈  GEMINI LIVE VOCAL MATRIX"))
        c2_lay.addWidget(self._dim_label("Select neural voice engine for live speech responses"))

        self._sel_voice = get_voice()
        self._voice_pills: dict[str, QPushButton] = {}
        v_row = QHBoxLayout(); v_row.setSpacing(6)
        for vname in AVAILABLE_VOICES:
            b = QPushButton(get_voice_display_name(vname))
            b.setFixedHeight(30)
            b.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, vn=vname: self._pick_voice(vn))
            v_row.addWidget(b)
            self._voice_pills[vname] = b
        c2_lay.addLayout(v_row)
        self._refresh_voice_pills()
        lay.addWidget(card2)

        # 3. Holographic Theme & Color Wheel Card
        card3, c3_lay = self._card_frame()
        c3_lay.addWidget(self._sec_label("◈  HOLOGRAPHIC ACCENT PALETTE"))
        c3_lay.addWidget(self._dim_label("Real-time UI re-theming — select a cyber preset or choose a custom hue"))

        # Presets row
        preset_row = QHBoxLayout(); preset_row.setSpacing(6)
        presets = [
            ("ARC CYAN",     "#00d4ff"),
            ("STARK GOLD",   "#ffaa00"),
            ("MATRIX GREEN", "#00ff88"),
            ("HULKBUSTER",   "#ff3355"),
            ("QUANTUM",      "#a855f7"),
            ("TITANIUM",     "#94a3b8"),
        ]
        for pname, phex in presets:
            pb = QPushButton(f"● {pname}")
            pb.setFixedHeight(26)
            pb.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
            pb.setCursor(Qt.CursorShape.PointingHandCursor)
            pb.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(0, 10, 18, 0.8); color: {phex};
                    border: 1px solid {phex}44; border-radius: 4px; padding: 0 8px;
                }}
                QPushButton:hover {{
                    border-color: {phex}; background: {phex}22;
                }}
            """)
            pb.clicked.connect(lambda _, h=phex: self._set_theme_color(h))
            preset_row.addWidget(pb)
        c3_lay.addLayout(preset_row)

        wheel_container = QHBoxLayout()
        self._initial_color = (cfg.get("ui_color") or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color = self._initial_color
        self._wheel = HueWheel(self._sel_color)
        self._wheel.hue_picked.connect(self._on_wheel_live)
        self._wheel.hue_committed.connect(self._on_wheel_commit)
        wheel_container.addWidget(self._wheel, alignment=Qt.AlignmentFlag.AlignCenter)

        wheel_ctrls = QVBoxLayout(); wheel_ctrls.setSpacing(8)
        wheel_ctrls.addWidget(self._dim_label("CUSTOM HEX CODE:"))
        self._hex_box = QLineEdit(self._sel_color)
        self._hex_box.setFont(QFont(UI_FONT, 10, QFont.Weight.Bold))
        self._hex_box.setFixedHeight(30)
        self._hex_box.setFixedWidth(120)
        self._hex_box.setStyleSheet(f"""
            QLineEdit {{ background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 2px 6px; }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._hex_box.textEdited.connect(self._on_hex_box_edited)
        wheel_ctrls.addWidget(self._hex_box)

        df_btn = QPushButton("RESET DEFAULT")
        df_btn.setFixedHeight(26)
        df_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_theme_color(DEFAULT_UI_COLOR))
        wheel_ctrls.addWidget(df_btn)

        hud_edit_btn = QPushButton("◉ CANVAS DRAG EDITOR")
        hud_edit_btn.setFixedHeight(26)
        hud_edit_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        hud_edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hud_edit_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px; padding: 0 8px; }}
            QPushButton:hover {{ border-color: {C.PRI}; }}
        """)
        hud_edit_btn.clicked.connect(lambda: (self.hide_hub(), self._main._open_hud_customize()))
        wheel_ctrls.addWidget(hud_edit_btn)

        wheel_ctrls.addStretch()
        wheel_container.addLayout(wheel_ctrls)
        wheel_container.addStretch()
        c3_lay.addLayout(wheel_container)

        # Grid brightness slider
        c3_lay.addSpacing(4)
        c3_lay.addWidget(self._dim_label("HUD RADAR GRID BRIGHTNESS:"))
        grid_row = QHBoxLayout()
        self._grid_slider = QSlider(Qt.Orientation.Horizontal)
        self._grid_slider.setRange(8, 90)
        self._grid_slider.setValue(int(self._main.hud.grid_brightness * 100))
        self._grid_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: {C.BORDER}; }}
            QSlider::handle:horizontal {{ width: 14px; margin: -5px 0;
                background: {C.PRI}; border: 1px solid {C.WHITE}; border-radius: 7px; }}
            QSlider::sub-page:horizontal {{ background: {C.PRI_DIM}; }}
        """)
        self._grid_lbl = QLabel(f"{self._grid_slider.value()}%")
        self._grid_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._grid_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._grid_slider.valueChanged.connect(self._on_grid_slider_changed)
        grid_row.addWidget(self._grid_slider)
        grid_row.addWidget(self._grid_lbl)
        c3_lay.addLayout(grid_row)

        lay.addWidget(card3)

        # 4. Custom Header Typography Card
        # Controls the three visible header text elements without changing
        # their positions or behaviour. Values are persisted in config.
        card4, c4_lay = self._card_frame()
        c4_lay.addWidget(self._sec_label("◈  CUSTOM HEADER"))
        c4_lay.addWidget(self._dim_label("Customize the font size of every visible header text element"))

        header_sizes = cfg.get("header_text_sizes", {})
        if not isinstance(header_sizes, dict):
            header_sizes = {}

        self._header_size_sliders = {}
        self._header_size_labels = {}
        header_size_specs = [
            ("LEFT BRANDING — P.R.I.N.C.E", "version", 8, 6, 28),
            ("CENTER TITLE — J.A.R.V.I.S", "title", 17, 8, 36),
            ("CENTER SUBTITLE", "subtitle", 7, 5, 24),
        ]

        for label_text, key, default, minimum, maximum in header_size_specs:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(self._dim_label(label_text))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setValue(int(header_sizes.get(key, default)))
            slider.setStyleSheet(f"""
                QSlider::groove:horizontal {{ height: 4px; background: {C.BORDER}; }}
                QSlider::handle:horizontal {{ width: 14px; margin: -5px 0;
                    background: {C.PRI}; border: 1px solid {C.WHITE}; border-radius: 7px; }}
                QSlider::sub-page:horizontal {{ background: {C.PRI_DIM}; }}
            """)
            size_lbl = QLabel(f"{slider.value()} px")
            size_lbl.setFixedWidth(48)
            size_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            size_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
            slider.valueChanged.connect(lambda value, k=key: self._on_header_size_changed(k, value))
            row.addWidget(slider, stretch=1)
            row.addWidget(size_lbl)
            self._header_size_sliders[key] = slider
            self._header_size_labels[key] = size_lbl
            c4_lay.addLayout(row)

        reset_header_btn = QPushButton("RESET HEADER SIZES")
        reset_header_btn.setFixedHeight(28)
        reset_header_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        reset_header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_header_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
        """)
        reset_header_btn.clicked.connect(self._reset_header_sizes)
        c4_lay.addWidget(reset_header_btn)
        lay.addWidget(card4)

        # Action Button Row
        act_row = QHBoxLayout(); act_row.setSpacing(10)
        apply_btn = QPushButton("▸  SAVE & APPLY IDENTITY")
        apply_btn.setFixedHeight(36)
        apply_btn.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI}; border-radius: 5px; padding: 0 16px;
            }}
            QPushButton:hover {{ background: rgba(0, 212, 255, 0.25); }}
        """)
        apply_btn.clicked.connect(self._apply_identity_settings)
        act_row.addWidget(apply_btn)

        self._identity_status = QLabel("")
        self._identity_status.setFont(QFont(UI_FONT, 8))
        self._identity_status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        act_row.addWidget(self._identity_status)
        act_row.addStretch()
        lay.addLayout(act_row)

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _pick_voice(self, name: str):
        self._sel_voice = name
        self._refresh_voice_pills()

    def _refresh_voice_pills(self):
        from memory.config_manager import get_voice_display_name
        for name, b in self._voice_pills.items():
            label = get_voice_display_name(name)
            if name == self._sel_voice:
                b.setText(f"✓ {label}")
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 4px;
                    }}
                """)
            else:
                b.setText(label)
                b.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(0, 10, 18, 0.7); color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 4px;
                    }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    def _set_theme_color(self, hex_val: str, update_wheel=True, preview=True):
        self._sel_color = hex_val.strip().lower()
        self._hex_box.setText(self._sel_color)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview:
            self._main._preview_ui_color(self._sel_color)

    def _on_wheel_live(self, hex_val: str):
        self._sel_color = hex_val
        self._hex_box.setText(hex_val)

    def _on_wheel_commit(self, hex_val: str):
        self._set_theme_color(hex_val, update_wheel=False, preview=True)

    def _on_hex_box_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
                self._set_theme_color(t, update_wheel=True, preview=True)
            except ValueError:
                pass

    def _on_grid_slider_changed(self, val: int):
        self._grid_lbl.setText(f"{val}%")
        self._main.hud.grid_brightness = val / 100.0
        self._main.hud._grid_cache = None
        self._main.hud.update()

    def _apply_header_sizes(self, sizes: dict[str, int], persist: bool = True):
        """Apply custom font sizes to all visible header text elements."""
        defaults = {"version": 8, "title": 17, "subtitle": 7}
        clean = {}
        for key, default in defaults.items():
            try:
                clean[key] = max(5, int(sizes.get(key, default)))
            except (TypeError, ValueError):
                clean[key] = default

        _branding_font = QFont(BRANDING_FONT, clean["version"], QFont.Weight.DemiBold)
        _branding_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        self._main._version_label.setFont(_branding_font)
        self._main._title_lbl.setFont(QFont(UI_FONT, clean["title"], QFont.Weight.Bold))
        self._main._sub_lbl.setFont(QFont(UI_FONT, clean["subtitle"]))

        if persist:
            data = _read_full_config()
            data["header_text_sizes"] = clean
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")

    def _on_header_size_changed(self, key: str, value: int):
        if hasattr(self, "_header_size_labels") and key in self._header_size_labels:
            self._header_size_labels[key].setText(f"{value} px")
        sizes = {k: slider.value() for k, slider in self._header_size_sliders.items()}
        self._apply_header_sizes(sizes, persist=False)

    def _reset_header_sizes(self):
        defaults = {"version": 8, "title": 17, "subtitle": 7}
        for key, value in defaults.items():
            slider = self._header_size_sliders.get(key)
            if slider:
                slider.setValue(value)
        self._apply_header_sizes(defaults, persist=True)

    def _apply_identity_settings(self):
        name = self._name_input.text().strip() or "JARVIS"
        user = self._user_input.text().strip()
        sub = self._sub_input.text().strip()
        voice = self._sel_voice
        color = self._sel_color
        header_sizes = {k: slider.value() for k, slider in self._header_size_sliders.items()}

        self._main._apply_name_update(name, user, color, voice)
        self._apply_header_sizes(header_sizes, persist=False)
        if sub:
            self._main._sub_lbl.setText(sub)
            cfg = _read_full_config()
            cfg["hud_subtitle"] = sub
            cfg["hud_grid_brightness"] = self._main.hud.grid_brightness
            cfg["header_text_sizes"] = header_sizes
            API_FILE.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        else:
            cfg = _read_full_config()
            cfg["hud_grid_brightness"] = self._main.hud.grid_brightness
            cfg["header_text_sizes"] = header_sizes
            API_FILE.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

        self._identity_status.setText("Configuration applied successfully ✓")
        QTimer.singleShot(3000, lambda: self._identity_status.setText(""))

    # ── TAB 1: AUDIO & VOICE ──────────────────────────────────────────────
    def _build_audio_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(10)

        from core.audio_devices import list_devices, DEFAULT_LABEL
        from memory.config_manager import get_input_device, get_output_device

        # 1. Audio Hardware Card
        card1, c1_lay = self._card_frame()
        c1_lay.addWidget(self._sec_label("◈  AUDIO HARDWARE INTERFACES"))
        c1_lay.addWidget(self._dim_label("Select physical or virtual microphones and speakers"))

        _combo_css = f"""
            QComboBox {{ background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px; }}
            QComboBox:hover {{ border-color: {C.BORDER_B}; }}
            QComboBox QAbstractItemView {{ background: #000c14; color: {C.TEXT};
                selection-background-color: {C.PRI_GHO}; border: 1px solid {C.BORDER}; }}
        """

        c1_lay.addWidget(self._dim_label("MICROPHONE (AUDIO INPUT)"))
        self._in_combo = QComboBox()
        self._in_combo.setFixedHeight(32)
        self._in_combo.setFont(QFont(UI_FONT, 9))
        self._in_combo.setStyleSheet(_combo_css)
        self._in_combo.addItem(DEFAULT_LABEL, "")
        for d in list_devices("input"):
            self._in_combo.addItem(d, d)
        cur_in = get_input_device()
        idx_in = self._in_combo.findData(cur_in) if cur_in else 0
        self._in_combo.setCurrentIndex(idx_in if idx_in >= 0 else 0)
        c1_lay.addWidget(self._in_combo)

        c1_lay.addWidget(self._dim_label("SPEAKERS (AUDIO OUTPUT)"))
        self._out_combo = QComboBox()
        self._out_combo.setFixedHeight(32)
        self._out_combo.setFont(QFont(UI_FONT, 9))
        self._out_combo.setStyleSheet(_combo_css)
        self._out_combo.addItem(DEFAULT_LABEL, "")
        for d in list_devices("output"):
            self._out_combo.addItem(d, d)
        cur_out = get_output_device()
        idx_out = self._out_combo.findData(cur_out) if cur_out else 0
        self._out_combo.setCurrentIndex(idx_out if idx_out >= 0 else 0)
        c1_lay.addWidget(self._out_combo)

        act_row1 = QHBoxLayout()
        apply_audio_btn = QPushButton("▸  APPLY AUDIO HARDWARE")
        apply_audio_btn.setFixedHeight(32)
        apply_audio_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        apply_audio_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_audio_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI}; border-radius: 4px; padding: 0 12px; }}
            QPushButton:hover {{ background: rgba(0, 212, 255, 0.2); }}
        """)
        apply_audio_btn.clicked.connect(self._apply_audio_devices)
        act_row1.addWidget(apply_audio_btn)

        self._audio_status = QLabel("")
        self._audio_status.setFont(QFont(UI_FONT, 8))
        self._audio_status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        act_row1.addWidget(self._audio_status)
        act_row1.addStretch()
        c1_lay.addLayout(act_row1)
        lay.addWidget(card1)

        # 2. Wake Word Engine Card
        card2, c2_lay = self._card_frame()
        c2_lay.addWidget(self._sec_label("◈  WAKE WORD DETECTION ENGINE ('Hey Jarvis')"))
        c2_lay.addWidget(self._dim_label("Zero-cloud on-device neural acoustic model wake gating"))

        self._wake_status_lbl = QLabel("Checking status...")
        self._wake_status_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        c2_lay.addWidget(self._wake_status_lbl)

        wake_btns_row = QHBoxLayout(); wake_btns_row.setSpacing(8)
        self._hub_wake_toggle_btn = QPushButton("🎙  WAKE WORD: TOGGLE")
        self._hub_wake_toggle_btn.setFixedHeight(32)
        self._hub_wake_toggle_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._hub_wake_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hub_wake_toggle_btn.clicked.connect(self._toggle_wake)
        wake_btns_row.addWidget(self._hub_wake_toggle_btn)

        self._hub_wake_sleep_btn = QPushButton("😴  SLEEP NOW")
        self._hub_wake_sleep_btn.setFixedHeight(32)
        self._hub_wake_sleep_btn.setFont(QFont(UI_FONT, 8))
        self._hub_wake_sleep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hub_wake_sleep_btn.clicked.connect(self._manual_wake_toggle)
        wake_btns_row.addWidget(self._hub_wake_sleep_btn)
        wake_btns_row.addStretch()
        c2_lay.addLayout(wake_btns_row)
        lay.addWidget(card2)

        # 3. Push-To-Talk Card
        card3, c3_lay = self._card_frame()
        c3_lay.addWidget(self._sec_label("◈  PUSH-TO-TALK MODE"))
        c3_lay.addWidget(self._dim_label("Microphone stays closed until you hold the key."))
        
        self._hub_ptt_btn = QPushButton("🎚  PUSH-TO-TALK: OFF")
        self._hub_ptt_btn.setFixedHeight(32)
        self._hub_ptt_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._hub_ptt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hub_ptt_btn.clicked.connect(self._toggle_ptt)
        
        c3_lay.addWidget(self._hub_ptt_btn)
        lay.addWidget(card3)
        self._refresh_ptt_btn()

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    
    def _refresh_ptt_btn(self):
        if not hasattr(self, '_hub_ptt_btn'): return
        from core.hotkey import chord_label
        from memory.config_manager import get_push_to_talk_enabled
        ptt = get_push_to_talk_enabled()
        self._hub_ptt_btn.setText(f"🎚  PUSH-TO-TALK: {chord_label()}" if ptt else "🎚  PUSH-TO-TALK: OFF")
        _on = f"QPushButton {{ background: #001a08; color: {C.GREEN}; border: 1px solid {C.GREEN_D}; border-radius: 4px; padding: 0 10px; }}"
        _off = f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px; }}"
        self._hub_ptt_btn.setStyleSheet(_on if ptt else _off)

    def _toggle_ptt(self):
        from memory.config_manager import get_push_to_talk_enabled, save_push_to_talk_enabled
        want = not get_push_to_talk_enabled()
        save_push_to_talk_enabled(want)
        self._refresh_ptt_btn()

    
    def _refresh_brief_btn(self):
        if not hasattr(self, '_hub_brief_btn'): return
        from memory.config_manager import get_brief_enabled
        enabled = get_brief_enabled()
        self._hub_brief_btn.setText("🗞  BRIEFING: ON" if enabled else "🗞  BRIEFING: OFF")
        _on = f"QPushButton {{ background: #001a08; color: {C.GREEN}; border: 1px solid {C.GREEN_D}; border-radius: 4px; padding: 0 10px; }}"
        _off = f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px; }}"
        self._hub_brief_btn.setStyleSheet(_on if enabled else _off)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        want = not get_brief_enabled()
        save_brief_enabled(want)
        self._refresh_brief_btn()

    def _toggle_wake(self):
        self._main._toggle_wake_word()
        self._refresh_wake_ui()

    def _manual_wake_toggle(self):
        self._main._tap_wake_manual()
        self._refresh_wake_ui()

    def _apply_audio_devices(self):
        from memory.config_manager import save_input_device, save_output_device
        in_dev = self._in_combo.currentData() or ""
        out_dev = self._out_combo.currentData() or ""
        save_input_device(in_dev)
        save_output_device(out_dev)
        self._main._on_audio_devices_applied()
        self._audio_status.setText("Hardware updated & session reconnected ✓")
        QTimer.singleShot(3500, lambda: self._audio_status.setText(""))

    def _refresh_wake_ui(self):
        st = self._main._wake_state()
        if not st.get("ready"):
            self._wake_status_lbl.setText("STATUS: ACOUSTIC MODEL NOT INSTALLED")
            self._wake_status_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
            self._hub_wake_toggle_btn.setText("⬇  DOWNLOAD WAKE MODEL (ONE-TIME)")
            self._hub_wake_toggle_btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(255, 170, 0, 0.15); color: {C.ACC2};
                    border: 1px solid {C.ACC2}; border-radius: 4px; padding: 0 10px; }}
            """)
            self._hub_wake_sleep_btn.hide()
        elif st.get("enabled"):
            self._wake_status_lbl.setText("STATUS: ACTIVE & LISTENING (Say 'Hey Jarvis')")
            self._wake_status_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
            self._hub_wake_toggle_btn.setText("🎙  WAKE WORD: ACTIVE (ON)")
            self._hub_wake_toggle_btn.setStyleSheet(f"""
                QPushButton {{ background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 4px; padding: 0 10px; }}
            """)
            self._hub_wake_sleep_btn.show()
            self._hub_wake_sleep_btn.setText("😴  SLEEP NOW" if st.get("awake") else "👂  WAKE NOW")
            self._hub_wake_sleep_btn.setStyleSheet(f"""
                QPushButton {{ background: rgba(0, 15, 25, 0.7); color: {C.TEXT_MED};
                    border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px; }}
                QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            """)
        else:
            self._wake_status_lbl.setText("STATUS: DISABLED (Direct Microphone Active)")
            self._wake_status_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            self._hub_wake_toggle_btn.setText("🎙  WAKE WORD: DISABLED (OFF)")
            self._hub_wake_toggle_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px; }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)
            self._hub_wake_sleep_btn.hide()

    # ── TAB 2: CORE & SYSTEM ──────────────────────────────────────────────
    def _build_core_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(10)

        cfg = _read_full_config()

        # 1. API Key Card
        card1, c1_lay = self._card_frame()
        c1_lay.addWidget(self._sec_label("◈  GEMINI NEURAL API AUTHORIZATION"))
        c1_lay.addWidget(self._dim_label("Google Gemini API token for LLM reasoning and multimodal live audio"))

        key_row = QHBoxLayout(); key_row.setSpacing(6)
        self._key_box = QLineEdit(cfg.get("gemini_api_key", ""))
        self._key_box.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_box.setPlaceholderText("AIzaSy...")
        self._key_box.setFont(QFont(UI_FONT, 9))
        self._key_box.setFixedHeight(32)
        self._key_box.setStyleSheet(f"""
            QLineEdit {{ background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 4px 8px; }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        key_row.addWidget(self._key_box, stretch=1)

        self._show_key_btn = QPushButton("👁 SHOW")
        self._show_key_btn.setFixedSize(68, 32)
        self._show_key_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        self._show_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_key_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px; }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """)
        self._show_key_btn.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self._show_key_btn)
        c1_lay.addLayout(key_row)

        c1_act = QHBoxLayout(); c1_act.setSpacing(8)
        save_key_btn = QPushButton("▸  SAVE & VALIDATE KEY")
        save_key_btn.setFixedHeight(32)
        save_key_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        save_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_key_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI}; border-radius: 4px; padding: 0 12px; }}
            QPushButton:hover {{ background: rgba(0, 212, 255, 0.2); }}
        """)
        save_key_btn.clicked.connect(self._save_api_key)
        c1_act.addWidget(save_key_btn)

        self._core_status = QLabel("")
        self._core_status.setFont(QFont(UI_FONT, 8))
        self._core_status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        c1_act.addWidget(self._core_status)
        c1_act.addStretch()
        c1_lay.addLayout(c1_act)
        lay.addWidget(card1)

        # 2. Operating System Card
        card2, c2_lay = self._card_frame()
        c2_lay.addWidget(self._sec_label("◈  OPERATING SYSTEM SUBSYSTEM"))
        det = {"darwin": "mac", "windows": "windows"}.get(_OS.lower(), "linux")
        saved_os = cfg.get("os_system", det)
        self._sel_os = saved_os

        c2_lay.addWidget(self._dim_label(f"Native environment detected: {_OS}"))
        os_row = QHBoxLayout(); os_row.setSpacing(8)
        self._os_pills: dict[str, QPushButton] = {}
        for osk, oslbl in [("windows", "⊞  Windows"), ("mac", "  macOS"), ("linux", "🐧  Linux")]:
            b = QPushButton(oslbl)
            b.setFixedHeight(32)
            b.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, k=osk: self._set_os_subsystem(k))
            os_row.addWidget(b)
            self._os_pills[osk] = b
        c2_lay.addLayout(os_row)
        self._refresh_os_pills()
        lay.addWidget(card2)

        # 3. System Automation Card
        card3, c3_lay = self._card_frame()
        c3_lay.addWidget(self._sec_label("◈  SYSTEM AUTOMATION & INTEGRATION"))

        auto_row = QHBoxLayout(); auto_row.setSpacing(8)
        self._hub_autostart_btn = QPushButton("◉  AUTO-START: OFF")
        self._hub_autostart_btn.setFixedHeight(32)
        self._hub_autostart_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._hub_autostart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hub_autostart_btn.clicked.connect(self._main._toggle_autostart)
        auto_row.addWidget(self._hub_autostart_btn)

        desk_btn = QPushButton("⊞  CREATE DESKTOP SHORTCUT")
        desk_btn.setFixedHeight(32)
        desk_btn.setFont(QFont(UI_FONT, 8))
        desk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        desk_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(0, 15, 25, 0.7); color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        desk_btn.clicked.connect(self._main._create_desktop_shortcut)
        auto_row.addWidget(desk_btn)

        fs_btn = QPushButton("⛶  FULLSCREEN [F11]")
        fs_btn.setFixedHeight(32)
        fs_btn.setFont(QFont(UI_FONT, 8))
        fs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fs_btn.setStyleSheet(f"""
            QPushButton {{ background: rgba(0, 15, 25, 0.7); color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        fs_btn.clicked.connect(self._main._toggle_fullscreen)
        auto_row.addWidget(fs_btn)
        c3_lay.addLayout(auto_row)
                
        brief_row = QHBoxLayout(); brief_row.setSpacing(8)
        self._hub_brief_btn = QPushButton("🗞  BRIEFING: OFF")
        self._hub_brief_btn.setFixedHeight(32)
        self._hub_brief_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._hub_brief_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hub_brief_btn.clicked.connect(self._toggle_brief)
        brief_row.addWidget(self._hub_brief_btn)
        
        brief_desc = QLabel("Read out unread emails & news on wake word")
        brief_desc.setStyleSheet(f"color: {C.TEXT_DIM};")
        brief_row.addWidget(brief_desc, stretch=1)
        c3_lay.addLayout(brief_row)
        self._refresh_brief_btn()

        lay.addWidget(card3)

        self._update_autostart_btn(self._main._check_autostart())

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _toggle_key_visibility(self):
        if self._key_box.echoMode() == QLineEdit.EchoMode.Password:
            self._key_box.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_key_btn.setText("🔒 HIDE")
        else:
            self._key_box.setEchoMode(QLineEdit.EchoMode.Password)
            self._show_key_btn.setText("👁 SHOW")

    def _save_api_key(self):
        k = self._key_box.text().strip()
        if not k:
            self._core_status.setText("Error: Key cannot be empty!")
            self._core_status.setStyleSheet(f"color: {C.RED}; background: transparent;")
            return
        self._main._on_setup_done(k, self._sel_os)
        self._core_status.setText("Key saved & core linked ✓")
        self._core_status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        QTimer.singleShot(3500, lambda: self._core_status.setText(""))

    def _set_os_subsystem(self, osk: str):
        self._sel_os = osk
        cfg = _read_full_config()
        cfg["os_system"] = osk
        API_FILE.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
        self._refresh_os_pills()

    def _refresh_os_pills(self):
        for k, b in self._os_pills.items():
            if k == self._sel_os:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI}; color: {C.DARK};
                        border: none; border-radius: 4px; font-weight: bold; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background: rgba(0, 15, 25, 0.7); color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 4px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_hub_autostart_btn'):
            return
        if enabled:
            self._hub_autostart_btn.setText("◉  AUTO-START: ON")
            self._hub_autostart_btn.setStyleSheet(f"""
                QPushButton {{ background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 4px; padding: 0 10px; }}
            """)
        else:
            self._hub_autostart_btn.setText("◉  AUTO-START: OFF")
            self._hub_autostart_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 10px; }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)

    # ── TAB 3: NEURAL MEMORY ──────────────────────────────────────────────
    def _build_memory_tab(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(8)

        card, c_lay = self._card_frame()
        c_lay.addWidget(self._sec_label("◈  NEURAL LONG-TERM MEMORY VAULT"))

        hdr_row = QHBoxLayout(); hdr_row.setSpacing(8)
        self._mem_search = QLineEdit()
        self._mem_search.setPlaceholderText("🔍 Filter stored memories by key or content...")
        self._mem_search.setFont(QFont(UI_FONT, 9))
        self._mem_search.setFixedHeight(30)
        self._mem_search.setStyleSheet(f"""
            QLineEdit {{ background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 2px 8px; }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._mem_search.textChanged.connect(self._filter_memories)
        hdr_row.addWidget(self._mem_search, stretch=1)

        self._mem_count_badge = QLabel("0 facts")
        self._mem_count_badge.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._mem_count_badge.setStyleSheet(f"""
            color: {C.PRI}; background: {C.PRI_GHO};
            border: 1px solid {C.PRI_DIM}; border-radius: 4px; padding: 4px 8px;
        """)
        hdr_row.addWidget(self._mem_count_badge)

        clear_btn = QPushButton("🗑 CLEAR ALL")
        clear_btn.setFixedHeight(30)
        clear_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
        """)
        clear_btn.clicked.connect(self._clear_all_memories)
        hdr_row.addWidget(clear_btn)
        c_lay.addLayout(hdr_row)

        self._mem_scroll = QScrollArea()
        self._mem_scroll.setWidgetResizable(True)
        self._mem_scroll_content = QWidget()
        self._mem_scroll_content.setStyleSheet("background: transparent;")
        self._mem_items_lay = QVBoxLayout(self._mem_scroll_content)
        self._mem_items_lay.setContentsMargins(0, 4, 4, 4)
        self._mem_items_lay.setSpacing(4)
        self._mem_scroll.setWidget(self._mem_scroll_content)
        c_lay.addWidget(self._mem_scroll, stretch=1)

        lay.addWidget(card, stretch=1)
        return container

    def _refresh_memory_tab(self):
        from memory.memory_manager import all_entries_for_ui
        self._cached_memories = all_entries_for_ui()
        self._mem_count_badge.setText(f"{len(self._cached_memories)} facts")
        self._filter_memories(self._mem_search.text())

    def _filter_memories(self, query: str = ""):
        query = (query or "").strip().lower()

        # Clear existing items safely
        while self._mem_items_lay.count():
            item = self._mem_items_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        items = getattr(self, "_cached_memories", [])
        matched = 0
        for r in items:
            key = str(r.get("key", ""))
            val = str(r.get("value", ""))
            cat = str(r.get("category", ""))
            upd = str(r.get("updated", "") or "—")

            if query and query not in key.lower() and query not in val.lower() and query not in cat.lower():
                continue
            matched += 1

            row_card = QFrame()
            row_card.setStyleSheet(f"""
                QFrame {{
                    background: rgba(0, 10, 16, 0.6);
                    border: 1px solid {C.BORDER};
                    border-radius: 4px;
                }}
                QFrame:hover {{ border-color: {C.BORDER_B}; }}
            """)
            rlay = QHBoxLayout(row_card)
            rlay.setContentsMargins(8, 6, 8, 6)
            rlay.setSpacing(8)

            cat_badge = QLabel(cat[:4].upper())
            cat_badge.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
            cat_badge.setStyleSheet(f"""
                color: {C.ACC2}; background: rgba(255, 204, 0, 0.1);
                border: 1px solid rgba(255, 204, 0, 0.3); border-radius: 3px; padding: 2px 4px;
            """)
            rlay.addWidget(cat_badge)

            txt_lbl = QLabel(f"<b style='color:{C.PRI}'>{key.replace('_', ' ')}</b>: <span style='color:{C.WHITE}'>{val}</span>")
            txt_lbl.setFont(QFont(UI_FONT, 8))
            txt_lbl.setWordWrap(True)
            txt_lbl.setStyleSheet("background: transparent;")
            rlay.addWidget(txt_lbl, stretch=1)

            upd_lbl = QLabel(upd)
            upd_lbl.setFont(QFont(UI_FONT, 7))
            upd_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            rlay.addWidget(upd_lbl)

            rm_btn = QPushButton("✕")
            rm_btn.setFixedSize(20, 20)
            rm_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            rm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rm_btn.setToolTip("Forget this memory")
            rm_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px; }}
                QPushButton:hover {{ color: {C.RED}; border-color: {C.RED}; }}
            """)
            rm_btn.clicked.connect(lambda _, c=cat, k=key: self._forget_memory(c, k))
            rlay.addWidget(rm_btn)

            self._mem_items_lay.addWidget(row_card)

        if matched == 0:
            empty_lbl = QLabel("No memories found.")
            empty_lbl.setFont(QFont(UI_FONT, 8))
            empty_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 10px;")
            self._mem_items_lay.addWidget(empty_lbl)

        self._mem_items_lay.addStretch()

    def _forget_memory(self, category: str, key: str):
        from memory.memory_manager import forget
        forget(key, category)
        self._refresh_memory_tab()

    def _clear_all_memories(self):
        try:
            p = BASE_DIR / "memory" / "long_term.json"
            if p.exists():
                p.write_text("{}", encoding="utf-8")
            self._refresh_memory_tab()
        except Exception:
            pass

    # ── TAB 4: PLUGINS & EXTENSIONS ───────────────────────────────────────
    def _build_plugins_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(10)

        # 1. Modular Plugins List
        card1, c1_lay = self._card_frame()
        c1_lay.addWidget(self._sec_label("◈  DISCOVERED SYSTEM PLUGINS"))
        c1_lay.addWidget(self._dim_label("Hot-pluggable extensions located in the /plugins repository"))

        self._plugins_box_lay = QVBoxLayout()
        self._plugins_box_lay.setSpacing(6)
        c1_lay.addLayout(self._plugins_box_lay)
        lay.addWidget(card1)

        # 2. Plugin Settings Form
        card2, c2_lay = self._card_frame()
        c2_lay.addWidget(self._sec_label("◈  PLUGIN CREDENTIALS & PARAMETERS"))
        c2_lay.addWidget(self._dim_label("Configure device connections, third-party API tokens, or hardware parameters"))

        self._plugin_settings_lay = QVBoxLayout()
        self._plugin_settings_lay.setSpacing(8)
        c2_lay.addLayout(self._plugin_settings_lay)
        lay.addWidget(card2)

        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _refresh_plugins_tab(self):
        # Clear plugins list
        while self._plugins_box_lay.count():
            item = self._plugins_box_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        plugins = self._main.get_plugins() if self._main.get_plugins else []
        if not plugins:
            no_p = QLabel("No external plugins discovered.")
            no_p.setFont(QFont(UI_FONT, 8))
            no_p.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            self._plugins_box_lay.addWidget(no_p)
        else:
            for p in plugins:
                row = QHBoxLayout(); row.setSpacing(8)
                lbl_text = p["name"] if p["valid"] else f"{p['name']} (⚠ {p['file']})"
                plbl = QLabel(lbl_text)
                plbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
                plbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.RED}; background: transparent;")
                row.addWidget(plbl, stretch=1)

                tbtn = QPushButton()
                tbtn.setFixedSize(70, 24)
                tbtn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
                if not p["valid"]:
                    tbtn.setText("BROKEN")
                    tbtn.setEnabled(False)
                else:
                    tbtn.setCursor(Qt.CursorShape.PointingHandCursor)
                    self._style_plugin_toggle(tbtn, p["enabled"])
                    tbtn.clicked.connect(lambda _, n=p["name"], b=tbtn: self._toggle_plugin(n, b))
                row.addWidget(tbtn)

                holder = QWidget()
                holder.setLayout(row)
                self._plugins_box_lay.addWidget(holder)

        # Clear plugin settings forms
        while self._plugin_settings_lay.count():
            item = self._plugin_settings_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        sections = self._main.get_plugin_settings() if self._main.get_plugin_settings else []
        if not sections:
            no_s = QLabel("No configurable plugin parameters declared.")
            no_s.setFont(QFont(UI_FONT, 8))
            no_s.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            self._plugin_settings_lay.addWidget(no_s)
        else:
            self._plugin_field_widgets = {}
            for sec in sections:
                ns = sec.get("namespace") or sec.get("plugin") or "plugin"
                sttl = QLabel(f"▸ {sec.get('title') or ns}")
                sttl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
                sttl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
                self._plugin_settings_lay.addWidget(sttl)

                values = sec.get("values") or {}
                for field in sec.get("fields", []):
                    if not isinstance(field, dict) or not field.get("key"):
                        continue
                    k = field["key"]
                    lbl = QLabel(field.get("label") or k)
                    lbl.setFont(QFont(UI_FONT, 7))
                    lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
                    self._plugin_settings_lay.addWidget(lbl)

                    w = QLineEdit(str(values.get(k, field.get("default", ""))))
                    w.setFont(QFont(UI_FONT, 9))
                    w.setFixedHeight(28)
                    w.setStyleSheet(f"""
                        QLineEdit {{ background: {C.PANEL2}; color: {C.WHITE};
                            border: 1px solid {C.BORDER}; border-radius: 4px; padding: 2px 6px; }}
                    """)
                    self._plugin_field_widgets[(ns, k)] = w
                    self._plugin_settings_lay.addWidget(w)

                save_p_btn = QPushButton(f"SAVE {ns.upper()} SETTINGS")
                save_p_btn.setFixedHeight(28)
                save_p_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
                save_p_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                save_p_btn.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 4px; padding: 0 10px; }}
                """)
                save_p_btn.clicked.connect(lambda _, n=ns: self._save_plugin_ns(n))
                self._plugin_settings_lay.addWidget(save_p_btn)

    def _style_plugin_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText("ACTIVE")
            btn.setStyleSheet(f"""
                QPushButton {{ background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 4px; }}
            """)
        else:
            btn.setText("DISABLED")
            btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 4px; }}
            """)

    def _toggle_plugin(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_v = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_v)
        self._style_plugin_toggle(btn, new_v)

    def _save_plugin_ns(self, ns: str):
        from memory.config_manager import save_plugin_config
        vals = {}
        for (n, k), w in getattr(self, "_plugin_field_widgets", {}).items():
            if n == ns:
                vals[k] = w.text().strip()
        save_plugin_config(ns, vals)

    # ── TAB 5: FACE SECURITY ──────────────────────────────────────────────
    def _build_face_security_tab(self) -> QWidget:
        """PIN-protected local face-authentication management UI."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(10)

        card, c_lay = self._card_frame()
        self._face_security_root = c_lay

        title = self._sec_label("🔐  FACE SECURITY")
        c_lay.addWidget(title)
        c_lay.addWidget(self._dim_label("Local-only biometric access control. Management requires the Master PIN."))

        self._face_locked_panel = QWidget()
        locked_lay = QVBoxLayout(self._face_locked_panel)
        locked_lay.setContentsMargins(4, 10, 4, 10)
        locked_lay.setSpacing(8)

        pin_lbl = QLabel("MASTER PIN")
        pin_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        pin_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        locked_lay.addWidget(pin_lbl)

        self._face_pin_input = QLineEdit()
        self._face_pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._face_pin_input.setPlaceholderText("Enter Master PIN")
        self._face_pin_input.setFixedHeight(34)
        self._face_pin_input.setFont(QFont(UI_FONT, 10))
        self._face_pin_input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.PANEL2}; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 5px; padding: 4px 9px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._face_pin_input.returnPressed.connect(self._unlock_face_security)
        locked_lay.addWidget(self._face_pin_input)

        unlock_btn = QPushButton("UNLOCK")
        unlock_btn.setFixedHeight(32)
        unlock_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        unlock_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: rgba(0, 212, 255, 0.18); border-color: {C.PRI}; }}
        """)
        unlock_btn.clicked.connect(self._unlock_face_security)
        locked_lay.addWidget(unlock_btn)

        self._face_pin_status = QLabel("")
        self._face_pin_status.setWordWrap(True)
        self._face_pin_status.setFont(QFont(UI_FONT, 7))
        self._face_pin_status.setStyleSheet(f"color: {C.RED}; background: transparent;")
        locked_lay.addWidget(self._face_pin_status)
        c_lay.addWidget(self._face_locked_panel)

        self._face_unlocked_panel = QWidget()
        self._face_unlocked_panel.hide()
        unlocked_lay = QVBoxLayout(self._face_unlocked_panel)
        unlocked_lay.setContentsMargins(4, 8, 4, 8)
        unlocked_lay.setSpacing(9)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self._sec_label("🔓  AUTHENTICATION"), stretch=1)
        self._face_auth_toggle = QPushButton()
        self._face_auth_toggle.setFixedSize(92, 28)
        self._face_auth_toggle.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        self._face_auth_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._face_auth_toggle.clicked.connect(self._toggle_face_authentication)
        status_row.addWidget(self._face_auth_toggle)
        unlocked_lay.addLayout(status_row)

        unlocked_lay.addWidget(self._sec_label("AUTHORIZED FACES"))
        self._face_list_lay = QVBoxLayout()
        self._face_list_lay.setSpacing(6)
        unlocked_lay.addLayout(self._face_list_lay)

        add_btn = QPushButton("＋  ADD FACE")
        add_btn.setFixedHeight(32)
        add_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI}; border-radius: 5px;
            }}
            QPushButton:hover {{ background: rgba(0, 212, 255, 0.18); }}
        """)
        add_btn.clicked.connect(self._add_face)
        unlocked_lay.addWidget(add_btn)

        change_pin_btn = QPushButton("CHANGE MASTER PIN")
        change_pin_btn.setFixedHeight(30)
        change_pin_btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        change_pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_pin_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 5px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """)
        change_pin_btn.clicked.connect(self._change_face_master_pin)
        unlocked_lay.addWidget(change_pin_btn)

        c_lay.addWidget(self._face_unlocked_panel)
        lay.addWidget(card)
        lay.addStretch()
        scroll.setWidget(container)
        return scroll

    def _face_security_modules(self):
        """Lazy-load security backends so ui.py stays usable without eager imports."""
        from plugins._face_security import get_face_security
        from plugins._face_database import get_face_database
        return get_face_security(), get_face_database()

    def _face_button(self, text: str, callback, danger: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(25)
        btn.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if danger:
            btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.RED}; border: 1px solid {C.RED}; border-radius: 4px; padding: 0 8px; }}
                QPushButton:hover {{ background: rgba(255, 51, 85, 0.10); }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.TEXT_MED}; border: 1px solid {C.BORDER}; border-radius: 4px; padding: 0 8px; }}
                QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
            """)
        btn.clicked.connect(callback)
        return btn

    def _style_face_auth_toggle(self, enabled: bool):
        if not self._face_auth_toggle:
            return
        if enabled:
            self._face_auth_toggle.setText("ON")
            self._face_auth_toggle.setStyleSheet(f"QPushButton {{ background: #001a08; color: {C.GREEN}; border: 1px solid {C.GREEN_D}; border-radius: 5px; }}")
        else:
            self._face_auth_toggle.setText("OFF")
            self._face_auth_toggle.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_DIM}; border: 1px solid {C.BORDER}; border-radius: 5px; }}")

    def _unlock_face_security(self):
        if self._face_security_unlocked:
            return
        pin = self._face_pin_input.text() if self._face_pin_input else ""
        if not pin:
            self._face_pin_status.setText("Enter the Master PIN.")
            return
        try:
            security, _ = self._face_security_modules()
            ok = bool(security.verify_pin(pin))
        except Exception:
            ok = False
        if not ok:
            self._face_pin_status.setText("Invalid Master PIN.")
            self._face_pin_input.selectAll()
            return
        self._face_security_unlocked = True
        self._face_pin_input.clear()
        self._face_pin_status.clear()
        self._face_locked_panel.hide()
        self._face_unlocked_panel.show()
        self._refresh_face_security_ui()

    def _lock_face_security_ui(self):
        self._face_security_unlocked = False
        if self._face_pin_input:
            self._face_pin_input.clear()
        if self._face_pin_status:
            self._face_pin_status.clear()
        if self._face_unlocked_panel:
            self._face_unlocked_panel.hide()
        if self._face_locked_panel:
            self._face_locked_panel.show()

    def _refresh_face_security_ui(self):
        if not self._face_security_unlocked:
            return
        try:
            from memory.config_manager import get_plugin_enabled
            enabled = bool(get_plugin_enabled("face_authenticate"))
            self._style_face_auth_toggle(enabled)
        except Exception:
            self._style_face_auth_toggle(False)

        while self._face_list_lay.count():
            item = self._face_list_lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        try:
            _, db = self._face_security_modules()
            faces = db.get_faces() or []
        except Exception as exc:
            err = QLabel(f"Face database unavailable: {exc}")
            err.setWordWrap(True)
            err.setStyleSheet(f"color: {C.RED}; background: transparent;")
            self._face_list_lay.addWidget(err)
            return

        if not faces:
            empty = QLabel("No authorized faces enrolled yet.")
            empty.setFont(QFont(UI_FONT, 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; padding: 8px 2px;")
            self._face_list_lay.addWidget(empty)
            return

        for face in faces:
            face_id = face.get("face_id") or face.get("id")
            number = face.get("face_number", "?")
            name = face.get("name") or f"Face {number}"

            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(8, 5, 8, 5)
            row_lay.setSpacing(5)
            row.setStyleSheet(f"QWidget {{ background: rgba(0, 15, 25, 0.45); border: 1px solid {C.BORDER}; border-radius: 5px; }}")

            lbl = QLabel(f"Face {number} — {name}")
            lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
            lbl.setStyleSheet("background: transparent; border: none; color: " + C.TEXT + ";")
            row_lay.addWidget(lbl, stretch=1)

            rename_btn = self._face_button("RENAME", lambda _, fid=face_id: self._rename_face(fid))
            remove_btn = self._face_button("REMOVE", lambda _, fid=face_id: self._remove_face(fid), danger=True)
            row_lay.addWidget(rename_btn)
            row_lay.addWidget(remove_btn)
            self._face_list_lay.addWidget(row)

    def _toggle_face_authentication(self):
        if not self._face_security_unlocked:
            return
        try:
            from memory.config_manager import get_plugin_enabled, save_plugin_enabled
            new_value = not bool(get_plugin_enabled("face_authenticate"))
            save_plugin_enabled("face_authenticate", new_value)
            self._style_face_auth_toggle(new_value)
        except Exception as exc:
            if self._face_pin_status:
                self._face_pin_status.setText(f"Unable to change Face Authentication: {exc}")

    def _add_face(self):
        if not self._face_security_unlocked:
            return
        name, ok = QInputDialog.getText(self, "ADD FACE", "Person name:")
        name = name.strip()
        if not ok or not name:
            return
        try:
            from plugins._face_recognizer import get_face_recognizer
            _, db = self._face_security_modules()
            recognizer = get_face_recognizer()

            # Existing recognizer captures multiple samples and returns embeddings.
            samples = recognizer.capture_face_samples(sample_count=5)
            if not samples:
                raise RuntimeError("No face samples were captured. Enrollment cancelled.")

            embedding = recognizer.average_embeddings(samples)
            if embedding is None:
                raise RuntimeError("Could not create a face embedding.")
                
            # Prevent duplicate face enrollment
            match = recognizer.find_best_match(embedding, db.get_face_embeddings(), threshold=0.45)
            if match and match.get("similarity", 0.0) >= 0.45:
                matched_face = db.get_face(match.get("face_id"))
                matched_name = matched_face.get("name") if matched_face else "Unknown"
                raise RuntimeError(f"Face already exists in database as '{matched_name}'.")

            # Existing FaceDatabase API is add_face(name, embedding).
            db.add_face(name, embedding)
            self._refresh_face_security_ui()
        except Exception as exc:
            QApplication.beep()
            QInputDialog.getText(self, "FACE ENROLLMENT", f"Enrollment failed:\n{exc}")

    def _rename_face(self, face_id):
        if not self._face_security_unlocked or not face_id:
            return
        try:
            _, db = self._face_security_modules()
            face = db.get_face(face_id)
            current = (face or {}).get("name", "")
            new_name, ok = QInputDialog.getText(self, "RENAME FACE", "New name:", text=current)
            new_name = new_name.strip()
            if not ok or not new_name:
                return
            db.rename_face(face_id, new_name)
            self._refresh_face_security_ui()
        except Exception as exc:
            QApplication.beep()
            self._face_pin_status.setText(f"Unable to rename face: {exc}")

    def _remove_face(self, face_id):
        if not self._face_security_unlocked or not face_id:
            return
        try:
            _, db = self._face_security_modules()
            face = db.get_face(face_id)
            name = (face or {}).get("name") or "this face"
            from PyQt6.QtWidgets import QMessageBox
            answer = QMessageBox.question(
                self, "REMOVE FACE", f"Remove {name} from Authorized Faces?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            db.remove_face(face_id)
            self._refresh_face_security_ui()
        except Exception as exc:
            QApplication.beep()
            self._face_pin_status.setText(f"Unable to remove face: {exc}")

    def _change_face_master_pin(self):
        if not self._face_security_unlocked:
            return
        try:
            security, _ = self._face_security_modules()
            current, ok = QInputDialog.getText(self, "CHANGE MASTER PIN", "Current PIN:", QLineEdit.EchoMode.Password)
            if not ok:
                return
            new_pin, ok = QInputDialog.getText(self, "CHANGE MASTER PIN", "New PIN:", QLineEdit.EchoMode.Password)
            if not ok or not new_pin:
                return
            confirm, ok = QInputDialog.getText(self, "CHANGE MASTER PIN", "Confirm new PIN:", QLineEdit.EchoMode.Password)
            if not ok:
                return
            if new_pin != confirm:
                self._face_pin_status.setText("New PINs do not match.")
                return
            if not security.change_pin(current, new_pin):
                self._face_pin_status.setText("Current PIN is invalid.")
                return
            self._face_pin_status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
            self._face_pin_status.setText("Master PIN changed successfully.")
        except Exception as exc:
            self._face_pin_status.setStyleSheet(f"color: {C.RED}; background: transparent;")
            self._face_pin_status.setText(f"Unable to change Master PIN: {exc}")

    # ── TAB 6: REMOTE ACCESS ──────────────────────────────────────────────
    def _build_remote_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(10)

        card, c_lay = self._card_frame()
        c_lay.addWidget(self._sec_label("◈  MOBILE TELEMETRY & DASHBOARD LINK"))
        c_lay.addWidget(self._dim_label("Scan with mobile camera to connect to the live assistant interface"))

        # QR and pairing details row
        pair_row = QHBoxLayout(); pair_row.setSpacing(16)

        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(176, 176)
        self._qr_label.setStyleSheet("background: white; border-radius: 8px; padding: 4px;")
        pair_row.addWidget(self._qr_label)

        details_v = QVBoxLayout(); details_v.setSpacing(6)
        details_v.addWidget(self._dim_label("ONE-TIME 6-DIGIT PAIRING KEY:"))

        self._key_lbl = QLabel("------")
        self._key_lbl.setFont(QFont(UI_FONT, 24, QFont.Weight.Bold))
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC}; background: {C.PANEL2};
            border: 1px solid {C.BORDER_B}; border-radius: 6px; padding: 6px;
            letter-spacing: 6px;
        """)
        details_v.addWidget(self._key_lbl)

        self._timer_lbl = QLabel("Key expires in --:--")
        self._timer_lbl.setFont(QFont(UI_FONT, 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        details_v.addWidget(self._timer_lbl)

        self._url_lbl = QLabel("URL: http://localhost:8000")
        self._url_lbl.setFont(QFont(UI_FONT, 7))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_v.addWidget(self._url_lbl)

        new_key_btn = QPushButton("⟳  GENERATE NEW KEY")
        new_key_btn.setFixedHeight(30)
        new_key_btn.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        new_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_key_btn.setStyleSheet(f"""
            QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                border: 1px solid {C.PRI}; border-radius: 4px; padding: 0 10px; }}
            QPushButton:hover {{ background: rgba(0, 212, 255, 0.2); }}
        """)
        new_key_btn.clicked.connect(self._refresh_remote_key)
        details_v.addWidget(new_key_btn)
        details_v.addStretch()

        pair_row.addLayout(details_v)
        c_lay.addLayout(pair_row)
        lay.addWidget(card)

        lay.addStretch()
        scroll.setWidget(container)

        self._qr_timer = QTimer(self)
        self._qr_timer.timeout.connect(self._remote_tick)
        return scroll

    def _refresh_remote_key(self):
        if not self._main.on_remote_clicked:
            return
        res = self._main.on_remote_clicked()
        if not res:
            return
        url, key = res[0], res[1]
        auto = res[2] if len(res) >= 3 else ""
        manual = res[3] if len(res) >= 4 else url

        self._key_lbl.setText(key)
        self._url_lbl.setText(f"URL: {manual or url}")
        self._expiry = time.time() + 600
        self._update_qr_image(auto or url)
        self._qr_timer.start(1000)
        self._remote_tick()

    def _update_qr_image(self, url_str: str):
        if not url_str:
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(box_size=5, border=2, error_correction=_qrmod.constants.ERROR_CORRECT_M)
            qr.add_data(url_str)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(px.scaled(168, 168, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            self._qr_label.setText(url_str[:28])

    def _remote_tick(self):
        rem = max(0, int(self._expiry - time.time()))
        m, s = divmod(rem, 60)
        self._timer_lbl.setText(f"Key expires in {m:02d}:{s:02d}")
        if rem == 0 and self._qr_timer:
            self._qr_timer.stop()

    def notify_phone_connected(self):
        if self._key_lbl:
            self._key_lbl.setText("CONNECTED")
            self._key_lbl.setStyleSheet(f"""
                color: {C.GREEN}; background: rgba(34, 197, 94, 0.1);
                border: 2px solid {C.GREEN}; border-radius: 6px; padding: 6px; letter-spacing: 3px;
            """)
        if self._timer_lbl:
            self._timer_lbl.setText("Phone linked — JARVIS online")
            self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    # ── TAB 7: JARVIS LOCK SYSTEM ─────────────────────────────────────────
    def _voice_lock_modules(self):
        from plugins._voice_lock import (
            list_challenges, add_challenge, replace_challenge, remove_challenge,
            get_challenge, verify_challenge_answer,
        )
        return list_challenges, add_challenge, replace_challenge, remove_challenge, get_challenge, verify_challenge_answer

    @staticmethod
    def _normalize_challenge_answer(text: str) -> str:
        text = unicodedata.normalize("NFKC", str(text or ""))
        text = text.casefold()
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _challenge_answer_matches(cls, spoken: str, expected: str) -> bool:
        a = cls._normalize_challenge_answer(spoken)
        b = cls._normalize_challenge_answer(expected)
        if not a or not b:
            return False
        if a == b:
            return True
        # Permit minor STT punctuation/spacing differences, but do not make
        # arbitrary long-answer challenges fuzzy enough to accept unrelated speech.
        if len(b) >= 8 and (a in b or b in a):
            return True
        aw, bw = a.split(), b.split()
        if len(bw) >= 4:
            common = sum(1 for w in set(aw) if w in set(bw))
            return common / max(1, len(set(bw))) >= 0.85
        return False

    def _build_lock_system_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(container)
        lay.setContentsMargins(4, 4, 12, 4)
        lay.setSpacing(10)

        card, c_lay = self._card_frame()
        c_lay.addWidget(self._sec_label("🔒  JARVIS LOCK SYSTEM"))
        c_lay.addWidget(self._dim_label("Startup access: Face Recognition → Master PIN → Voice Challenge. Create your own questions and answers locally."))

        self._voice_locked_panel = QWidget()
        ll = QVBoxLayout(self._voice_locked_panel)
        ll.setContentsMargins(4, 10, 4, 10)
        ll.setSpacing(8)
        ll.addWidget(self._dim_label("MASTER PIN REQUIRED"))
        self._voice_pin_input = QLineEdit()
        self._voice_pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._voice_pin_input.setPlaceholderText("Enter Master PIN")
        self._voice_pin_input.setFixedHeight(34)
        self._voice_pin_input.setFont(QFont(UI_FONT, 10))
        self._voice_pin_input.setStyleSheet(f"QLineEdit {{ background: {C.PANEL2}; color: {C.WHITE}; border: 1px solid {C.BORDER}; border-radius: 5px; padding: 4px 9px; }} QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")
        self._voice_pin_input.returnPressed.connect(self._unlock_voice_settings)
        ll.addWidget(self._voice_pin_input)
        b = QPushButton("UNLOCK SECURITY SETTINGS")
        b.setFixedHeight(32)
        b.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        b.clicked.connect(self._unlock_voice_settings)
        ll.addWidget(b)
        self._voice_pin_status = QLabel("")
        self._voice_pin_status.setStyleSheet(f"color: {C.RED}; background: transparent;")
        ll.addWidget(self._voice_pin_status)
        c_lay.addWidget(self._voice_locked_panel)

        self._voice_unlocked_panel = QWidget()
        self._voice_unlocked_panel.hide()
        ul = QVBoxLayout(self._voice_unlocked_panel)
        ul.setContentsMargins(4, 8, 4, 8)
        ul.setSpacing(9)
        ul.addWidget(self._sec_label("🎙️  VOICE LOCK CHALLENGES"))
        self._voice_count_lbl = self._dim_label("")
        ul.addWidget(self._voice_count_lbl)
        self._voice_list_lay = QVBoxLayout()
        self._voice_list_lay.setSpacing(6)
        ul.addLayout(self._voice_list_lay)

        add = QPushButton("＋  ADD QUESTION")
        add.setFixedHeight(34)
        add.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        add.clicked.connect(lambda: self._open_voice_challenge_editor())
        ul.addWidget(add)
        note = self._dim_label("Create your own question and correct answer. At startup JARVIS asks one saved question and unlocks only when your spoken answer matches it.")
        note.setWordWrap(True)
        ul.addWidget(note)
        c_lay.addWidget(self._voice_unlocked_panel)

        lay.addWidget(card)
        lay.addStretch()
        scroll.setWidget(container)
        self._voice_settings_unlocked = False
        self._voice_capture_dialog = None
        return scroll

    def _open_voice_challenge_editor(self, challenge_id: str | None = None):
        if not self._voice_settings_unlocked:
            return
        try:
            *_, get_challenge, _verify = self._voice_lock_modules()
        except Exception as exc:
            self._voice_pin_status.setText(f"Voice lock unavailable: {exc}")
            return
        existing = get_challenge(challenge_id) if challenge_id else None
        dlg = QDialog(self)
        dlg.setWindowTitle("EDIT VOICE CHALLENGE" if existing else "ADD VOICE CHALLENGE")
        dlg.setModal(True)
        dlg.setMinimumWidth(520)
        dlg.setStyleSheet(f"QDialog {{ background:{C.BG}; color:{C.TEXT}; }} QLabel {{ color:{C.TEXT}; }} QLineEdit, QTextEdit {{ background:{C.PANEL2}; color:{C.WHITE}; border:1px solid {C.BORDER_B}; border-radius:5px; padding:8px; }} QPushButton {{ background:{C.PANEL2}; color:{C.PRI}; border:1px solid {C.BORDER_B}; border-radius:5px; padding:8px 16px; font-weight:bold; }}")
        form = QVBoxLayout(dlg)
        form.setContentsMargins(22, 20, 22, 18); form.setSpacing(10)
        form.addWidget(self._sec_label("QUESTION"))
        q = QTextEdit(); q.setFixedHeight(95); q.setPlaceholderText("Example: What is the main purpose behind building your JARVIS?")
        if existing: q.setPlainText(str(existing.get("question", "")))
        form.addWidget(q)
        form.addWidget(self._sec_label("CORRECT ANSWER"))
        a = QTextEdit(); a.setFixedHeight(95); a.setPlaceholderText("Type the answer you will say aloud.")
        if existing: a.setPlainText(str(existing.get("answer_hint", "")))
        form.addWidget(a)
        hint = self._dim_label("The answer is stored as a salted hash. Keep it memorable but not obvious to other people.")
        hint.setWordWrap(True); form.addWidget(hint)
        buttons = QHBoxLayout(); buttons.addStretch(1)
        cancel = QPushButton("CANCEL"); save = QPushButton("SAVE")
        buttons.addWidget(cancel); buttons.addWidget(save); form.addLayout(buttons)
        cancel.clicked.connect(dlg.reject)

        def save_it():
            question = q.toPlainText().strip(); answer = a.toPlainText().strip()
            if len(question) < 5 or len(answer) < 2:
                hint.setText("Question and answer are required."); return
            try:
                _list, add_challenge, replace_challenge, _remove, _get, _verify = self._voice_lock_modules()
                ok = (replace_challenge(challenge_id, question, answer) if existing else add_challenge(question, answer))
                if not ok:
                    hint.setText("Could not save. Check for duplicates or the maximum challenge limit."); return
                dlg.accept(); self._refresh_voice_lock_ui()
            except Exception as exc:
                hint.setText(f"Save failed: {exc}")
        save.clicked.connect(save_it)
        dlg.exec()

    def _remove_voice_challenge(self, challenge_id: str):
        if not self._voice_settings_unlocked:
            return
        try:
            _list, _add, _replace, remove_challenge, _get, _verify = self._voice_lock_modules()
            if remove_challenge(challenge_id): self._refresh_voice_lock_ui()
        except Exception as exc:
            self._voice_pin_status.setText(f"Unable to remove challenge: {exc}")

    def _verify_master_pin_for_voice(self) -> bool:
        pin = self._voice_pin_input.text().strip() if self._voice_pin_input else ""
        if not pin:
            self._voice_pin_status.setText("Enter the Master PIN.")
            return False
        try:
            security, _ = self._face_security_modules()
            ok = bool(security.verify_pin(pin))
        except Exception:
            ok = False
        if not ok:
            self._voice_pin_status.setText("Invalid Master PIN.")
            self._voice_pin_input.selectAll()
            return False
        self._voice_settings_unlocked = True
        self._voice_pin_input.clear()
        self._voice_pin_status.clear()
        self._voice_locked_panel.hide()
        self._voice_unlocked_panel.show()
        self._refresh_voice_lock_ui()
        return True

    def _unlock_voice_settings(self):
        if not self._voice_settings_unlocked:
            self._verify_master_pin_for_voice()

    def _lock_voice_settings_ui(self):
        self._voice_settings_unlocked = False
        if getattr(self, "_voice_pin_input", None):
            self._voice_pin_input.clear()
        if getattr(self, "_voice_pin_status", None):
            self._voice_pin_status.clear()
        if getattr(self, "_voice_unlocked_panel", None):
            self._voice_unlocked_panel.hide()
        if getattr(self, "_voice_locked_panel", None):
            self._voice_locked_panel.show()

    def _refresh_voice_lock_ui(self):
        if not getattr(self, "_voice_settings_unlocked", False):
            return
        try:
            list_challenges, _, _, _, _, _ = self._voice_lock_modules()
            challenges = list_challenges()
        except Exception as exc:
            self._voice_count_lbl.setText(f"Voice lock unavailable: {exc}"); return
        self._voice_count_lbl.setText(f"{len(challenges)} challenge(s) saved")
        while self._voice_list_lay.count():
            item = self._voice_list_lay.takeAt(0); w = item.widget()
            if w: w.deleteLater()
        for ch in challenges:
            row = QWidget(); rl = QHBoxLayout(row); rl.setContentsMargins(0, 2, 0, 2); rl.setSpacing(6)
            label = QLabel(f"❓ {ch.get('question', 'Untitled question')}"); label.setWordWrap(True); label.setStyleSheet(f"color:{C.TEXT}; background:{C.PANEL2}; border:1px solid {C.BORDER}; border-radius:5px; padding:8px;")
            rl.addWidget(label, 1)
            edit = QPushButton("EDIT"); edit.setFixedWidth(58); edit.clicked.connect(lambda _=False, cid=ch['id']: self._open_voice_challenge_editor(cid)); rl.addWidget(edit)
            rem = QPushButton("DELETE"); rem.setFixedWidth(68); rem.clicked.connect(lambda _=False, cid=ch['id']: self._remove_voice_challenge(cid)); rl.addWidget(rem)
            self._voice_list_lay.addWidget(row)

    # ── Tab Switching & Navigation ────────────────────────────────────────
    def set_tab(self, tab_identifier):
        tab_map = {
            "identity": 0, "theme": 0, 0: 0,
            "audio": 1, "voice": 1, 1: 1,
            "core": 2, "system": 2, 2: 2,
            "memory": 3, 3: 3,
            "plugins": 4, "extensions": 4, 4: 4,
            "face": 5, "face_security": 5, "security": 5, 5: 5,
            "remote": 6, "telemetry": 6, 6: 6,
            "lock": 7, "lock_system": 7, "jarvis_lock": 7, 7: 7,
        }
        idx = tab_map.get(tab_identifier, 0)
        self._active_tab_idx = idx
        self._stack.setCurrentIndex(idx)
        self._refresh_tab_styles()

        # Contextual refresh on tab entry
        if idx == 1:
            self._refresh_wake_ui()
        elif idx == 3:
            self._refresh_memory_tab()
        elif idx == 4:
            self._refresh_plugins_tab()
        elif idx == 5:
            # Security controls are always relocked when entering the tab.
            self._lock_face_security_ui()
        elif idx == 6:
            self._refresh_remote_key()
        elif idx == 7:
            self._lock_voice_settings_ui()
            self._refresh_voice_lock_ui()

    def _refresh_tab_styles(self):
        for idx, btn in enumerate(self._tab_buttons):
            if idx == self._active_tab_idx:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(0, 212, 255, 0.16);
                        color: {C.PRI};
                        border: 1px solid {C.PRI_DIM};
                        border-left: 4px solid {C.PRI};
                        border-radius: 6px;
                        text-align: left;
                        padding-left: 12px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: rgba(0, 15, 25, 0.5);
                        color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER};
                        border-left: 4px solid transparent;
                        border-radius: 6px;
                        text-align: left;
                        padding-left: 12px;
                    }}
                    QPushButton:hover {{
                        background: rgba(0, 212, 255, 0.08);
                        color: {C.TEXT};
                        border-color: {C.BORDER_B};
                    }}
                """)

    def reposition(self):
        p = self.parentWidget() or self._main.centralWidget()
        if p is None:
            return
        w = min(self._OW, max(680, p.width() - 32))
        h = min(self._OH, max(480, p.height() - 32))
        x = max(0, (p.width() - w) // 2)
        y = max(0, (p.height() - h) // 2)
        self.setGeometry(x, y, w, h)

    def show_hub(self, tab="identity"):
        self.reposition()
        self.set_tab(tab)
        self.show()
        self.raise_()
        self._main._drawer_btn.setChecked(True)

    def hide_hub(self):
        # Never retain the unlocked Face Security management state after
        # Settings is closed. The backend PIN hash remains persistent; only
        # this UI session state is cleared.
        self._lock_face_security_ui()
        self._lock_voice_settings_ui()
        self.hide()
        self._main._drawer_btn.setChecked(False)
        self.closed.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide_hub()
            e.accept()
            return
        super().keyPressEvent(e)


class LocationGlobe(QWidget):
    """In-app satellite globe with search, location permission, and flight animation."""
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending: str | None = None
        self._loaded = False
        self._started = False
        self.setStyleSheet(f"background: {C.BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 6, 7, 7)
        layout.setSpacing(5)

        bar = QHBoxLayout()
        title = QLabel("◉  GLOBAL SATELLITE NAVIGATION")
        title.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent; letter-spacing: 1px;")
        bar.addWidget(title)
        bar.addStretch(1)
        self._place = QLineEdit()
        self._place.setPlaceholderText("Search any city, address, or landmark…")
        self._place.setMinimumWidth(220)
        self._place.returnPressed.connect(self._search)
        self._place.setStyleSheet(
            f"QLineEdit {{ color: {C.WHITE}; background: {C.PANEL}; border: 1px solid {C.BORDER_B}; "
            "border-radius: 3px; padding: 5px 8px; }"
        )
        bar.addWidget(self._place)
        self._add_button(bar, "FLY TO", self._search)
        self._add_button(bar, "MY LOCATION", self._locate)
        self._add_button(bar, "CLOSE  ✕", lambda: self.close_requested.emit())
        layout.addLayout(bar)

        self.view = QWebEngineView(self)
        self.page = self.view.page()
        self.view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self.view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, True
        )
        if hasattr(self.page, "permissionRequested"):
            self.page.permissionRequested.connect(self._permission_requested)
        elif hasattr(self.page, "featurePermissionRequested"):
            self.page.featurePermissionRequested.connect(self._legacy_permission_requested)
        self.view.loadFinished.connect(self._page_loaded)
        layout.addWidget(self.view, 1)

    def _add_button(self, bar, label: str, callback):
        button = QPushButton(label)
        button.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(f"""
            QPushButton {{ color: {C.PRI}; background: {C.PANEL};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px; padding: 5px 8px; }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        button.clicked.connect(callback)
        bar.addWidget(button)

    def navigate(self, place: str = ""):
        self._pending = str(place or "").strip()
        if not self._started:
            self._started = True
            map_path = Path(__file__).resolve().parent / "core" / "location_globe.html"
            self.view.load(QUrl.fromLocalFile(str(map_path)))
        if self._loaded:
            self._run_pending()

    def _page_loaded(self, ok: bool):
        self._loaded = bool(ok)
        if ok:
            QTimer.singleShot(500, self._run_pending)

    def _run_pending(self):
        if not self._loaded or self._pending is None:
            return
        place, self._pending = self._pending, None
        if place:
            import json as _json
            self.view.page().runJavaScript(f"window.jarvisFlyTo({_json.dumps(place)});")
        else:
            self.view.page().runJavaScript("window.jarvisLocate();")

    def _search(self):
        value = self._place.text().strip()
        if value:
            self._pending = value
            self._run_pending()

    def _locate(self):
        self._pending = ""
        self._run_pending()

    def _permission_requested(self, permission):
        from PyQt6.QtWebEngineCore import QWebEnginePermission
        if permission.permissionType() != QWebEnginePermission.PermissionType.Geolocation:
            permission.deny()
            return
        from PyQt6.QtWidgets import QMessageBox
        answer = QMessageBox.question(
            self, "ALLOW DEVICE LOCATION?",
            "JARVIS will use this PC's location service to mark your position. "
            "Map imagery requests reveal the viewed map area to the map provider. "
            "The location is not saved by Jarvis. Allow location access?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            permission.grant()
        else:
            permission.deny()

    def _legacy_permission_requested(self, origin, feature):
        if feature != QWebEnginePage.Feature.Geolocation:
            self.page.setFeaturePermission(
                origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
            )
            return
        from PyQt6.QtWidgets import QMessageBox
        answer = QMessageBox.question(
            self, "ALLOW DEVICE LOCATION?",
            "JARVIS will use this PC's location service to mark your position. "
            "Map imagery requests reveal the viewed map area to the map provider. "
            "The location is not saved by Jarvis. Allow location access?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        policy = (QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                  if answer == QMessageBox.StandardButton.Yes
                  else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser)
        self.page.setFeaturePermission(origin, feature, policy)


class MainWindow(QMainWindow):
    # Voice-lock backend helper belongs to MainWindow because startup Voice Unlock
    # runs here. JarvisSettingsHub has its own helper for Settings UI.
    def _voice_lock_modules(self):
        from plugins._voice_lock import (
            list_challenges, add_challenge, replace_challenge, remove_challenge,
            get_challenge, verify_challenge_answer,
        )
        return (
            list_challenges, add_challenge, replace_challenge, remove_challenge,
            get_challenge, verify_challenge_answer,
        )

    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _location_sig   = pyqtSignal(str)        # place name; empty means current location
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _confirm_sig    = pyqtSignal(str, str)   # (title, detail) — irreversible-action gate
    _confirm_hide_sig = pyqtSignal()
    _wake_dl_sig    = pyqtSignal(bool, str)  # wake-word install finished (ok, message)
    _startup_pin_sig = pyqtSignal()          # show startup Master PIN dialog on Qt thread
    _startup_voice_sig = pyqtSignal(bool, str)  # startup voice capture result

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path

        # Give the window and Windows taskbar the same JARVIS identity.  The
        # icon lives beside the app configuration so it works in both source
        # runs and frozen distributions.
        if APP_ICON.is_file():
            self.setWindowIcon(QIcon(str(APP_ICON)))

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or "JARVIS").strip()
        _display = self._assistant_name.upper()

        # Apply the saved UI colour BEFORE panels/stylesheets are built
        _ui_color = (_cfg.get("ui_color") or "").strip()
        if _ui_color and _ui_color.lower() != DEFAULT_UI_COLOR:
            apply_ui_accent(_ui_color)

        self.setWindowTitle(f"{_display} — {APP_VERSION}")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop JARVIS mid-speech
        self.on_voice_change   = None   # callable: () -> None — rebuild session with new voice
        self.on_audio_device_change = None  # callable: () -> None — reopen audio streams
        self._confirm_overlay  = None   # live ConfirmBanner, if one is on screen
        self.get_plugins       = None   # callable: () -> list[dict], set by JarvisLive
        self.get_plugin_settings = None # callable: () -> list[dict] settings schemas, set by JarvisLive
        self.on_wake_toggle    = None   # callable: (enable: bool) -> str, set by JarvisLive
        self.on_wake_manual    = None   # callable: () -> None — manual sleep/wake
        self.wake_get_state    = None   # callable: () -> dict {enabled, awake, ready}
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None
        self._hud_editor = None
        self._hud_edit_mode = False
        self._hud_drag = None
        self._hud_resize = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()

        # Center column: HUD + resizable content panel via QSplitter
        self.hud = HudCanvas(face_path, _display)
        self.hud.grid_brightness = max(0.08, min(0.9, float(_cfg.get("hud_grid_brightness", 0.42))))
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._content_panel = self._build_content_panel()

        # Live camera container — replaces HUD when camera stream is active
        _cam_cont = QWidget()
        _cam_cont.setStyleSheet("background: #000308;")
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(8, 5, 8, 5)
        _cam_title = QLabel("◈  CAMERA FEED")
        _cam_title.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = QPushButton("✕  CLOSE")
        _cam_x.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        _cam_x.setCursor(Qt.CursorShape.PointingHandCursor)
        _cam_x.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT_DIM}; background: transparent;
                border: none; padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {C.PRI}; }}
        """)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # Stack: 0 = animated HUD, 1 = live camera
        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self.hud)
        self._hud_cam_stack.addWidget(_cam_cont)
        self._location_globe = LocationGlobe(self)
        self._location_globe.close_requested.connect(lambda: self._hud_cam_stack.setCurrentIndex(0))
        self._hud_cam_stack.addWidget(self._location_globe)

        self._center_split = QSplitter(Qt.Orientation.Vertical)
        self._center_split.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._center_split.addWidget(self._hud_cam_stack)
        self._center_split.setStretchFactor(0, 3)
        self._center_split.setCollapsible(0, False)
        body.addWidget(self._center_split, stretch=5)

        self._right_panel = self._build_right_panel()
        self._right_panel.hide()
        self._left_panel.setParent(central)
        self._right_panel.setParent(central)
        self._left_panel.setObjectName("FloatingSystemPanel")
        self._right_panel.setObjectName("FloatingActivityPanel")
        self._left_panel.setStyleSheet(
            f"QWidget#FloatingSystemPanel {{ background: {C.DARK}; "
            f"border: 1px solid {C.BORDER_B}; border-radius: 6px; }}"
        )
        self._right_panel.setStyleSheet(
            f"QWidget#FloatingActivityPanel {{ background: {C.DARK}; "
            f"border: 1px solid {C.BORDER_B}; border-radius: 6px; }}"
        )
        self._left_panel.hide()
        self._content_panel.setParent(central)
        self._content_panel.setObjectName("FloatingResultsPanel")
        self._content_panel.setStyleSheet(f"""
            QWidget#FloatingResultsPanel {{ background: {C.DARK};
                border: 1px solid {C.BORDER_B}; border-radius: 6px; }}
        """)
        self._content_panel.hide()

        root.addLayout(body, stretch=1)
        # Bottom-centered ChatGPT-style composer. The file drop zone remains
        # available as a hidden helper so uploaded-file state stays compatible
        # with the rest of the assistant.
        self._chat_bar = self._build_chat_bar()
        self._position_chat_bar()
        self._chat_bar.raise_()
        self._time_panel = self._build_time_panel()
        self._position_time_panel()
        self._time_panel.raise_()
        QTimer.singleShot(0, self._position_header_tools)

        # Settings Command Center (Unified futuristic modal overlay)
        self._settings_hub = JarvisSettingsHub(self, parent=central)
        self._update_autostart_btn(self._check_autostart())
        try:
            from memory.config_manager import save_brief_enabled
            save_brief_enabled(False)
        except Exception:
            pass

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metric update timer
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._location_sig.connect(self._show_location)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._confirm_sig.connect(self._show_confirm_banner)
        self._confirm_hide_sig.connect(self._hide_confirm_banner)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._wake_dl_sig.connect(self._on_wake_install_done)
        self._startup_pin_pending = None
        self._startup_pin_sig.connect(self._show_startup_pin_dialog)
        self._startup_voice_sig.connect(self._on_startup_voice_result)
        self._startup_dialog = None
        self._startup_voice_busy = False
        self._cam_stop = threading.Event()

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        self._overlay: SetupOverlay | None = None
        self._ready = self._check_config()
        if not self._ready:
            old_palette = current_palette()
            apply_ui_accent(C.RED)
            retheme_all_widgets(old_palette, current_palette())
            self._api_warning.setText("API KEY NOT FOUND — OPEN SETTINGS")
            self._api_warning.show()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)

        # ── Force window to foreground on startup (Windows) ───────────────
        # PyQt6's show()/raise_()/activateWindow() are not always enough on
        # Windows — the OS may leave the window behind the current foreground
        # app. A short single-shot timer fires after the event loop starts,
        # at which point SetForegroundWindow reliably brings the window up.
        QTimer.singleShot(200, self._force_to_front)

    def _force_to_front(self) -> None:
        """Bring the window to the foreground immediately after startup."""
        self.raise_()
        self.activateWindow()
        if _OS == "Windows":
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            except Exception:
                pass


    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )

    # --- Live camera stream in HUD area ------------------------------------
    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            # Reuse camera index detected by screen_processor (cached in api_keys.json)
            cam_idx = 0
            try:
                import json as _j
                cfg = _j.loads((CONFIG_DIR / "api_keys.json").read_text())
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return
            # warm-up frames
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # ------------------------------------------------------------------
    # Icon generation — arc-reactor style, rendered with Pillow
    # ------------------------------------------------------------------
    @staticmethod
    def _build_jarvis_icon(out_path: Path) -> bool:
        """
        Render a JARVIS arc-reactor icon at 4× resolution and downsample
        for crisp results at all sizes. Saves a multi-res .ico to out_path.
        Returns True on success.
        """
        try:
            import math
            import PIL.Image
            import PIL.ImageDraw
            import PIL.ImageFilter
        except ImportError:
            return False

        CYAN   = (0, 212, 255)
        DIM    = (0, 100, 140)
        DARK   = (0, 6, 10)
        GLOW   = (0, 160, 200)
        WHITE  = (220, 240, 255)

        def _render(sz: int) -> PIL.Image.Image:
            S  = sz * 4                     # draw at 4× then downscale
            img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d   = PIL.ImageDraw.Draw(img)
            cx = cy = S // 2

            # ── filled background circle ──────────────────────────────────
            R = S // 2 - 2
            d.ellipse([cx-R, cy-R, cx+R, cy+R], fill=(*DARK, 255))

            # ── outer border ring ─────────────────────────────────────────
            lw = max(2, S // 40)
            d.ellipse([cx-R, cy-R, cx+R, cy+R],
                      outline=(*CYAN, 220), width=lw)

            # ── mid decorative ring ───────────────────────────────────────
            R2 = int(R * 0.72)
            d.ellipse([cx-R2, cy-R2, cx+R2, cy+R2],
                      outline=(*DIM, 180), width=max(1, lw // 2))

            # ── 6 radial spokes (hex bolt) ────────────────────────────────
            R_inner = int(R * 0.30)
            R_outer = int(R * 0.62)
            spoke_w = max(1, S // 80)
            for i in range(6):
                angle = math.radians(i * 60 - 30)
                x1 = cx + int(R_inner * math.cos(angle))
                y1 = cy + int(R_inner * math.sin(angle))
                x2 = cx + int(R_outer * math.cos(angle))
                y2 = cy + int(R_outer * math.sin(angle))
                d.line([x1, y1, x2, y2], fill=(*GLOW, 200), width=spoke_w)

            # ── 6 tick marks on outer ring ────────────────────────────────
            for i in range(6):
                angle = math.radians(i * 60)
                for dr in range(lw * 2):
                    rx = (R - lw - dr)
                    d.point(
                        [cx + int(rx * math.cos(angle)),
                         cy + int(rx * math.sin(angle))],
                        fill=(*WHITE, 220),
                    )

            # ── inner glowing ring ────────────────────────────────────────
            Ri = int(R * 0.26)
            d.ellipse([cx-Ri, cy-Ri, cx+Ri, cy+Ri],
                      outline=(*CYAN, 255), width=max(2, lw))

            # ── bright glow soft blur applied before core ─────────────────
            # (draw a slightly larger cyan circle on a separate layer)
            glow_layer = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gd = PIL.ImageDraw.Draw(glow_layer)
            Rc = int(R * 0.13)
            gd.ellipse([cx-Rc*2, cy-Rc*2, cx+Rc*2, cy+Rc*2],
                       fill=(*CYAN, 110))
            glow_layer = glow_layer.filter(PIL.ImageFilter.GaussianBlur(S // 14))
            img = PIL.Image.alpha_composite(img, glow_layer)
            d   = PIL.ImageDraw.Draw(img)

            # ── core dot ──────────────────────────────────────────────────
            d.ellipse([cx-Rc, cy-Rc, cx+Rc, cy+Rc], fill=(*WHITE, 255))

            # ── downscale to target size ──────────────────────────────────
            return img.resize((sz, sz), PIL.Image.LANCZOS)

        try:
            sizes  = [256, 128, 64, 48, 32, 16]
            frames = [_render(s) for s in sizes]
            frames[0].save(
                out_path,
                format="ICO",
                append_images=frames[1:],
                sizes=[(s, s) for s in sizes],
            )
            return True
        except Exception as e:
            print(f"[Shortcut] ⚠️  Icon generation failed: {e}")
            return False

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "J.A.R.V.I.S AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "J.A.R.V.I.S AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create a desktop shortcut on Windows / macOS / Linux.
        Never opens a terminal, console, or PowerShell window on any platform.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # Arc-reactor icon (.ico — also exported as .png for Linux/macOS)
        ico_path = Path(__file__).resolve().parent / "config" / "jarvis_app.ico"
        if not ico_path.exists():
            self._build_jarvis_icon(ico_path)

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "J.A.R.V.I.S.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "J.A.R.V.I.S.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "JARVIS"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>JARVIS</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.jarvis.assistant</string>\n'
                    '  <key>CFBundleName</key><string>J.A.R.V.I.S</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Export .ico → .png for better desktop integration
                png_path = ico_path.with_suffix(".png")
                if not png_path.exists() and ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "J.A.R.V.I.S.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=J.A.R.V.I.S\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Desktop shortcut created.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        if hasattr(self, '_chat_bar'):
            self._position_chat_bar()
        if hasattr(self, '_time_panel'):
            self._position_time_panel()
        if hasattr(self, '_header_tools'):
            self._position_header_tools()
        if hasattr(self, '_drawer_btn'):
            self._position_settings_button()
        if hasattr(self, '_header_center'):
            self._position_header_center()
        self._position_floating_panels()
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()
        # Settings Command Center — reposition if open
        if hasattr(self, '_settings_hub') and self._settings_hub.isVisible():
            self._settings_hub.reposition()

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")

        try:
            boot_t  = psutil.boot_time()
            elapsed = time.time() - boot_t
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            self._uptime_lbl.setText(f"UP  {h:02d}:{m:02d}")
        except Exception:
            self._uptime_lbl.setText("UP  --:--")

        try:
            proc_count = len(psutil.pids())
            self._proc_lbl.setText(f"PROC  {proc_count}")
        except Exception:
            self._proc_lbl.setText("PROC  --")


    def _build_header(self) -> QWidget:
        w = QWidget()
        self._header_widget = w
        w.setFixedHeight(54)
        w.setStyleSheet(f"background: {C.DARK};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont(UI_FONT, 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        cfg = _read_full_config()
        self._version_label = _EditableHeaderLabel(
            cfg.get("app_version") or APP_VERSION
        )
        _branding_font = QFont(BRANDING_FONT, 8, QFont.Weight.DemiBold)
        _branding_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        self._version_label.setFont(_branding_font)
        self._version_label.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._version_label.setToolTip("Double-click to rename")
        self._version_label.double_clicked.connect(lambda: self._edit_header_name("version"))
        lay.addWidget(self._version_label)
        lay.addSpacing(8)
        self._drawer_btn = QPushButton("⚙")
        self._drawer_btn.setFixedSize(28, 28)
        self._drawer_btn.setFont(QFont(UI_FONT, 12))
        self._drawer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._drawer_btn.setToolTip("System Configuration & Settings")
        self._drawer_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
            QPushButton:checked {{ color: {C.PRI}; border-color: {C.PRI}; background: {C.PRI_GHO}; }}
        """)
        self._drawer_btn.setCheckable(True)
        self._drawer_btn.clicked.connect(self._toggle_settings_hub)

        # Settings is a screen-level control, not part of the header layout.
        # Reparent it to the central HUD surface so it can stay at the
        # bottom-left edge across resize/fullscreen without changing its
        # appearance or click behaviour.
        lay.addStretch()
        self._drawer_btn.setParent(self.centralWidget())
        self._position_settings_button()
        self._drawer_btn.raise_()

        mid = QVBoxLayout(); mid.setSpacing(1)
        _disp = self._assistant_name.upper()
        self._title_lbl = _EditableHeaderLabel(_disp)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setFont(QFont(UI_FONT, 17, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._title_lbl.setToolTip("Double-click to rename")
        self._title_lbl.double_clicked.connect(lambda: self._edit_header_name("assistant"))
        mid.addWidget(self._title_lbl)
        _sub_text = cfg.get("hud_subtitle") or (
            "Just A Rather Very Intelligent System"
            if _disp in ("JARVIS", "J.A.R.V.I.S")
            else "Personal AI Assistant"
        )
        self._sub_lbl = QLabel(_sub_text)
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setFont(QFont(UI_FONT, 7))
        self._sub_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")

        # Restore user-customized header typography, if configured.
        header_sizes = cfg.get("header_text_sizes", {})
        if isinstance(header_sizes, dict):
            try:
                _branding_size = max(5, int(header_sizes.get("version", 8)))
                _branding_font = QFont(BRANDING_FONT, _branding_size, QFont.Weight.DemiBold)
                _branding_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
                self._version_label.setFont(_branding_font)
                self._title_lbl.setFont(QFont(UI_FONT, max(5, int(header_sizes.get("title", 17))), QFont.Weight.Bold))
                self._sub_lbl.setFont(QFont(UI_FONT, max(5, int(header_sizes.get("subtitle", 7)))))
            except (TypeError, ValueError):
                pass
        mid.addWidget(self._sub_lbl)
        self._header_center = QWidget(w)
        self._header_center.setLayout(mid)
        self._header_center.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._api_warning = QLabel("")
        self._api_warning.setFont(QFont(UI_FONT, 6, QFont.Weight.Bold))
        self._api_warning.setStyleSheet(f"color: {C.RED}; background: transparent;")
        self._api_warning.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._api_warning.setCursor(Qt.CursorShape.PointingHandCursor)
        self._api_warning.mousePressEvent = lambda _: self._settings_hub.show_hub("core") if hasattr(self, '_settings_hub') else None
        self._api_warning.hide()
        lay.addWidget(self._api_warning)

        tool_style = f"""
            QPushButton {{
                background: {C.PANEL2}; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 16px;
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}
        """
        self._log_btn = _DraggableButton("▤", w)
        self._log_btn.setFixedSize(34, 34)
        self._log_btn.setFont(QFont(UI_FONT, 14))
        self._log_btn.setToolTip("Show activity log; drag to move")
        self._log_btn.setCursor(Qt.CursorShape.SizeAllCursor)
        self._log_btn.setStyleSheet(tool_style)
        self._log_btn.clicked.connect(self._toggle_activity_log)

        self._content_btn = _DraggableButton("◈", w)
        self._content_btn.setFixedSize(34, 34)
        self._content_btn.setFont(QFont(UI_FONT, 13))
        self._content_btn.setToolTip("Show assistant results; drag to move")
        self._content_btn.setCursor(Qt.CursorShape.SizeAllCursor)
        self._content_btn.setStyleSheet(tool_style)
        self._content_btn.clicked.connect(self._toggle_content)
        self._header_tools = [self._log_btn, self._content_btn]
        QTimer.singleShot(0, self._position_header_tools)
        QTimer.singleShot(0, self._position_header_center)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%I:%M:%S %p"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_time_panel(self) -> QWidget:
        panel = _MovableOverlay(self.centralWidget())
        panel.setFixedSize(150, 48)
        panel.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(0)
        self._clock_lbl = QLabel("12:00:00 AM", panel)
        self._clock_lbl.setFont(QFont(UI_FONT, 14, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("", panel)
        self._date_lbl.setFont(QFont(UI_FONT, 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._date_lbl)
        return panel

    def _position_time_panel(self):
        cw = self.centralWidget()
        self._time_panel.setGeometry(cw.width() - 174, cw.height() - 60, 150, 48)
        self._time_panel.user_placed = False

    def _position_header_center(self):
        if not hasattr(self, "_header_center"):
            return
        header = self._header_widget
        width = min(360, max(240, header.width() // 3))
        self._header_center.setGeometry(
            (header.width() - width) // 2, 1, width, header.height() - 2
        )

    def _save_hud_layout(self):
        data = _read_full_config()
        def normalized(widget):
            parent = widget.parentWidget()
            pw = max(1, parent.width())
            ph = max(1, parent.height())
            return {
                "x": widget.x() / pw, "y": widget.y() / ph,
                "w": widget.width() / pw, "h": widget.height() / ph,
            }
        widgets = {}
        for name, widget in self._hud_targets().items():
            widgets[name] = normalized(widget)
        data["hud_layout"] = {
            "time": normalized(self._time_panel),
            "tools": [normalized(b) for b in self._header_tools],
            "widgets": widgets,
        }
        data["hud_subtitle"] = self._sub_lbl.text()
        data["hud_grid_brightness"] = self.hud.grid_brightness
        API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
        self._log.append_log("SYS: HUD layout saved.")

    def _reset_hud_layout(self):
        data = _read_full_config()
        data.pop("hud_layout", None)
        API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
        self._time_panel.user_placed = False
        for button in self._header_tools:
            button.user_placed = False
        self._position_time_panel()
        self._position_header_tools()

    def _hud_targets(self) -> dict[str, QWidget]:
        """Visible UI surfaces allowed to move in HUD edit mode.

        The chat composer and the central radar are intentionally absent.
        """
        targets = {
            "header": self._header_widget,
            "version_label": self._version_label,
            "assistant_title": self._title_lbl,
            "assistant_subtitle": self._sub_lbl,
            "right_panel": self._right_panel,
            "content_panel": self._content_panel,
        }
        return targets

    def _restore_hud_geometry(self):
        cfg = _read_full_config().get("hud_layout", {})
        widgets = cfg.get("widgets", {}) if isinstance(cfg, dict) else {}
        for name, geometry in widgets.items():
            widget = self._hud_targets().get(name)
            if widget and all(key in geometry for key in ("x", "y", "w", "h")):
                parent = widget.parentWidget()
                if max(abs(float(geometry[key])) for key in ("x", "y", "w", "h")) <= 1.5:
                    pw, ph = max(1, parent.width()), max(1, parent.height())
                    geometry = {
                        "x": float(geometry["x"]) * pw,
                        "y": float(geometry["y"]) * ph,
                        "w": float(geometry["w"]) * pw,
                        "h": float(geometry["h"]) * ph,
                    }
                widget.setGeometry(
                    int(geometry["x"]), int(geometry["y"]),
                    max(80, int(geometry["w"])), max(40, int(geometry["h"])),
                )

    def _set_hud_edit_mode(self, enabled: bool):
        self._hud_edit_mode = enabled
        for widget in self._hud_targets().values():
            if enabled:
                widget.installEventFilter(self)
                widget.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                widget.removeEventFilter(self)
                widget.unsetCursor()
        if enabled:
            self._log.append_log("SYS: HUD edit mode active. Drag or resize highlighted UI surfaces.")
        else:
            self._save_hud_layout()

    def eventFilter(self, watched, event):
        if not self._hud_edit_mode or watched not in self._hud_targets().values():
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            point = event.position()
            if point.x() >= watched.width() - 20 and point.y() >= watched.height() - 20:
                self._hud_resize = (watched, event.globalPosition().toPoint(), watched.geometry())
            else:
                self._hud_drag = (watched, event.globalPosition().toPoint())
            watched.raise_()
            return True
        if event.type() == QEvent.Type.MouseMove:
            current = event.globalPosition().toPoint()
            if self._hud_resize:
                target, origin, geometry = self._hud_resize
                delta = current - origin
                target.setGeometry(
                    geometry.x(), geometry.y(),
                    max(80, geometry.width() + delta.x()),
                    max(40, geometry.height() + delta.y()),
                )
                return True
            if self._hud_drag:
                target, origin = self._hud_drag
                target.move(target.pos() + current - origin)
                self._hud_drag = (target, current)
                return True
        if event.type() == QEvent.Type.MouseButtonRelease:
            self._hud_drag = None
            self._hud_resize = None
            return True
        return super().eventFilter(watched, event)

    def _open_hud_customize(self):
        cfg = _read_full_config()
        if self._hud_editor:
            self._hud_editor.show()
            self._hud_editor.raise_()
            return
        editor = QWidget(self.centralWidget())
        editor.setObjectName("HudEditor")
        editor.setStyleSheet(f"""
            QWidget#HudEditor {{ background: {C.PANEL2}; border: 1px solid {C.PRI};
                border-radius: 6px; }}
            QLineEdit {{ background: {C.DARK}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; padding: 4px; }}
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.PRI}; }}
        """)
        lay = QVBoxLayout(editor)
        lay.setContentsMargins(10, 8, 10, 8)
        title = QLabel("HUD EDITOR")
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(title)
        note = QLabel("Drag optional interface panels. Time and activity controls stay fixed.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(note)
        subtitle = QLineEdit(cfg.get("hud_subtitle") or self._sub_lbl.text())
        subtitle.setPlaceholderText("Brand subtitle")
        lay.addWidget(subtitle)
        grid_label = QLabel("GRID BRIGHTNESS")
        grid_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(grid_label)
        grid_slider = QSlider(Qt.Orientation.Horizontal)
        grid_slider.setRange(8, 90)
        grid_slider.setValue(int(self.hud.grid_brightness * 100))
        grid_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: {C.BORDER}; }}
            QSlider::handle:horizontal {{ width: 14px; margin: -5px 0;
                background: {C.PRI}; border: 1px solid {C.WHITE}; border-radius: 7px; }}
            QSlider::sub-page:horizontal {{ background: {C.PRI_DIM}; }}
        """)
        lay.addWidget(grid_slider)
        row = QHBoxLayout()
        save = QPushButton("SAVE")
        reset = QPushButton("RESET")
        close = QPushButton("CLOSE")
        row.addWidget(save)
        row.addWidget(reset)
        row.addWidget(close)
        lay.addLayout(row)
        def save_hud():
            self._sub_lbl.setText(subtitle.text().strip())
            self.hud.grid_brightness = grid_slider.value() / 100.0
            self.hud._grid_cache = None
            self.hud.update()
            self._set_hud_edit_mode(False)
            self._save_hud_layout()

        save.clicked.connect(save_hud)
        reset.clicked.connect(self._reset_hud_layout)
        close.clicked.connect(lambda: (self._set_hud_edit_mode(False), editor.hide()))
        editor.adjustSize()
        editor.setGeometry(18, 70, 300, editor.sizeHint().height())
        editor.show()
        editor.raise_()
        self._hud_editor = editor
        self._set_hud_edit_mode(True)
        self._log.append_log("SYS: HUD edit mode active.")

    def _edit_header_name(self, kind: str):
        if kind == "version":
            current = self._version_label.text()
            title = "Rename app version"
        else:
            current = self._assistant_name
            title = "Rename assistant"
        value, accepted = QInputDialog.getText(self, title, "Name:", text=current)
        value = value.strip()
        if not accepted or not value:
            return
        try:
            data = _read_full_config()
            if kind == "version":
                data["app_version"] = value
                self._version_label.setText(value)
                self.setWindowTitle(f"{self._assistant_name.upper()} — {value}")
            else:
                data["assistant_name"] = value
                self._apply_name_update(
                    value,
                    data.get("user_name", ""),
                    data.get("ui_color", ""),
                    data.get("voice_name", ""),
                )
                return
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Header renamed — {value}")
        except Exception as e:
            self._log.append_log(f"ERR: Header rename failed — {e}")

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(_LEFT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(6)

        hdr = QLabel("◈ SYS MONITOR")
        hdr.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent; "
                          f"border-bottom: 1px solid {C.BORDER}; padding-bottom: 4px;")
        lay.addWidget(hdr)
        lay.addSpacing(2)

        self._bar_cpu = MetricBar("CPU", C.PRI)
        self._bar_mem = MetricBar("MEM", C.ACC2)
        self._bar_net = MetricBar("NET", C.GREEN)
        self._bar_gpu = MetricBar("GPU", C.ACC)
        self._bar_tmp = MetricBar("TMP", "#ff6688")

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        info_panel = QWidget()
        info_panel.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;"
        )
        ip_lay = QVBoxLayout(info_panel)
        ip_lay.setContentsMargins(6, 5, 6, 5)
        ip_lay.setSpacing(3)

        self._uptime_lbl = QLabel("UP  --:--")
        self._uptime_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        ip_lay.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont(UI_FONT, 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        ip_lay.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_lbl = QLabel(f"OS  {os_name}")
        os_lbl.setFont(QFont(UI_FONT, 8))
        os_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        ip_lay.addWidget(os_lbl)

        lay.addWidget(info_panel)
        lay.addSpacing(4)

        lay.addStretch()

        for txt, col in [
            ("AI CORE\nACTIVE",  C.GREEN),
            ("SEC\nCLEARED",     C.PRI),
            ("PROTOCOL\n" + APP_PROTOCOL,   C.TEXT_DIM),
        ]:
            lbl = QLabel(txt)
            lbl.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {col}; background: {C.PANEL2};"
                f"border: 1px solid {C.BORDER_A}; border-radius: 3px; padding: 4px;"
            )
            lay.addWidget(lbl)

        return w
    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(_RIGHT_W)
        w.setStyleSheet(f"background: {C.DARK}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        def _sec(txt):
            l = QLabel(f"▸ {txt}")
            l.setFont(QFont(UI_FONT, 7, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            return l

        lay.addWidget(_sec("ACTIVITY LOG"))
        self._log = LogWidget()
        self._log.hide()
        lay.addWidget(self._log, stretch=1)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        return w

    def _build_chat_bar(self) -> QWidget:
        """Build the bottom-centered composer for commands and quick actions."""
        self._drop_zone = FileDropZone(self.centralWidget())
        self._drop_zone.file_selected.connect(self._on_file_selected)
        self._drop_zone.hide()

        bar = QWidget(self.centralWidget())
        bar.setObjectName("ChatComposer")
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"""
            QWidget#ChatComposer {{
                background: transparent;
                border: 1px solid {C.PRI_DIM};
                border-radius: 14px;
            }}
            QLineEdit {{
                background: #00070d; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 8px; padding: 0 12px;
                selection-background-color: {C.PRI_GHO};
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 9px;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO}; color: {C.PRI}; border-color: {C.PRI_DIM};
            }}
        """)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(38, 38)
        add_btn.setFont(QFont(UI_FONT, 18, QFont.Weight.Bold))
        add_btn.setToolTip("Attach a file")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._browse_file)
        lay.addWidget(add_btn)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message J.A.R.V.I.S...")
        self._input.setFont(QFont(UI_FONT, 10))
        self._input.setFixedHeight(38)
        self._input.returnPressed.connect(self._send)
        lay.addWidget(self._input, stretch=1)

        self._mute_btn = QPushButton("🔊")
        self._mute_btn.setFixedSize(38, 38)
        self._mute_btn.setFont(QFont(UI_FONT, 14, QFont.Weight.Bold))
        self._mute_btn.setToolTip("Mute or unmute microphone")
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        lay.addWidget(self._mute_btn)

        self._interrupt_btn = QPushButton("🤐")
        self._interrupt_btn.setFixedSize(38, 38)
        self._interrupt_btn.setFont(QFont("Segoe UI Emoji", 13))
        self._interrupt_btn.setToolTip("Interrupt J.A.R.V.I.S.")
        self._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        lay.addWidget(self._interrupt_btn)

        send = QPushButton("↑")
        send.setFixedSize(38, 38)
        send.setFont(QFont(UI_FONT, 17, QFont.Weight.Bold))
        send.setToolTip("Send message")
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._send)
        lay.addWidget(send)

        self._style_mute_btn()
        return bar

    def _position_chat_bar(self):
        if not hasattr(self, '_chat_bar'):
            return
        cw = self.centralWidget()
        width = min(760, max(460, cw.width() - 80))
        height = self._chat_bar.height()
        x = (cw.width() - width) // 2
        y = cw.height() - height - 34
        self._chat_bar.setGeometry(x, y, width, height)

    def _position_header_tools(self):
        if not hasattr(self, '_header_tools'):
            return
        x = self._header_widget.width() - 16 - len(self._header_tools) * 42
        for index, button in enumerate(self._header_tools):
            button.move(x + index * 42, 10)
            button.user_placed = False

    def _position_settings_button(self):
        """Keep the existing Settings button at the central HUD's bottom-left."""
        if not hasattr(self, '_drawer_btn') or not self._drawer_btn:
            return
        cw = self.centralWidget()
        if cw is None:
            return
        margin = 12
        self._drawer_btn.move(
            margin,
            max(margin, cw.height() - self._drawer_btn.height() - margin),
        )
        self._drawer_btn.raise_()

    def _position_floating_panels(self):
        if not hasattr(self, '_right_panel'):
            return
        cw = self.centralWidget()
        margin = 14
        width = min(340, max(260, cw.width() // 4))
        activity_h = min(330, max(180, cw.height() // 3))
        x = cw.width() - width - margin
        y = 64
        activity_visible = self._right_panel.isVisible()
        if activity_visible:
            self._right_panel.setGeometry(x, y, width, activity_h)
        if self._content_panel.isVisible():
            results_y = y + activity_h + 8 if activity_visible else y
            self._content_panel.setGeometry(x, results_y, width, 260)

    def _browse_file(self):
        self._drop_zone._browse()

    def _toggle_activity_log(self):
        visible = not self._log.isVisible()
        self._right_panel.setVisible(visible)
        self._log.setVisible(visible)
        self._position_floating_panels()
        if visible:
            self._right_panel.raise_()
        self._log_btn.setToolTip("Hide activity log" if visible else "Show activity log")

    def _toggle_content(self):
        visible = not self._content_panel.isVisible()
        self._content_panel.setVisible(visible)
        self._position_floating_panels()
        if visible:
            self._content_panel.raise_()
        self._content_btn.setToolTip(
            "Hide assistant results" if visible else "Show assistant results"
        )

    def _toggle_settings_hub(self, checked: bool = False):
        if hasattr(self, '_settings_hub'):
            if self._settings_hub.isVisible():
                self._settings_hub.hide_hub()
            else:
                self._settings_hub.show_hub("identity")

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(5)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question…")
        self._input.setFont(QFont(UI_FONT, 9))
        self._input.setFixedHeight(30)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: #000d14; color: {C.WHITE};
                border: 1px solid {C.BORDER}; border-radius: 3px; padding: 3px 7px;
            }}
            QLineEdit:focus {{ border: 1px solid {C.PRI}; }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(30, 30)
        send.setFont(QFont(UI_FONT, 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = QWidget()
        w.setObjectName("ContentPanel")
        w.setStyleSheet(f"""
            QWidget#ContentPanel {{
                background: {C.PANEL};
                border-top: 1px solid {C.BORDER_B};
            }}
        """)
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(5)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont(UI_FONT, 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("ASSISTANT RESULTS")
        self._content_title_lbl.setFont(QFont(UI_FONT, 8, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont(UI_FONT, 7))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = QPushButton("DISMISS  ✕")
        dismiss.setFont(QFont(UI_FONT, 7))
        dismiss.setFixedHeight(18)
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 2px; padding: 0 5px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont(UI_FONT, 8))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        self._content_panel.show()
        self._position_floating_panels()
        self._content_panel.raise_()
        self._content_btn.setToolTip("Show new assistant results")

    def _show_location(self, place: str):
        self._hud_cam_stack.setCurrentIndex(2)
        self._location_globe.navigate(place)

    def show_location(self, place: str = ""):
        """Thread-safe request to display current location or fly to a place."""
        self._location_sig.emit(str(place or "")[:240])

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        self._input.setPlaceholderText(
            f"{icon}  {p.name} attached — ask {self._assistant_name} what to do..."
        )
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def notify_phone_connected(self) -> None:
        if hasattr(self, '_settings_hub'):
            self._settings_hub.notify_phone_connected()
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if hasattr(self, '_settings_hub'):
            self._settings_hub.show_hub("remote")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "JARVIS_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.jarvis.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "jarvis.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "JARVIS_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "JARVIS_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.jarvis.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.jarvis.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "jarvis.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  AUTO-START: ON")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            self._autostart_btn.setText("◉  AUTO-START: OFF")
            self._autostart_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}
            """)

    # ── Wake word settings ───────────────────────────────────────────────────

    def _wake_state(self) -> dict:
        """Combined state for the two wake-word buttons. Readiness is a cheap,
        deterministic on-disk check now (see core.wake_word.is_ready), so there
        is nothing to cache — the button never flickers to a stale value."""
        if self.wake_get_state:
            try:
                s = self.wake_get_state()
                return {"ready": bool(s.get("ready")),
                        "enabled": bool(s.get("enabled")),
                        "awake": bool(s.get("awake"))}
            except Exception:
                pass
        # Before JarvisLive has wired its callback (drawer built at startup).
        ready, enabled = False, False
        try:
            from core.wake_word import is_ready
            from memory.config_manager import get_wake_word_enabled
            ready, enabled = is_ready(), get_wake_word_enabled()
        except Exception:
            pass
        return {"ready": ready, "enabled": enabled, "awake": True}

    def _refresh_wake_btns(self):
        if not hasattr(self, '_wake_btn'):
            return
        st = self._wake_state()
        _on = f"""
            QPushButton {{ background: #001a08; color: {C.GREEN};
                border: 1px solid {C.GREEN_D}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ background: #002010; }}"""
        _off = f"""
            QPushButton {{ background: transparent; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                text-align: left; padding: 0 8px; }}
            QPushButton:hover {{ color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"""
        self._wake_btn.setEnabled(True)
        if not st["ready"]:
            self._wake_btn.setText("⬇  WAKE WORD: DOWNLOAD")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()
        elif st["enabled"]:
            self._wake_btn.setText("🎙  WAKE WORD: ON")
            self._wake_btn.setStyleSheet(_on)
            self._wake_sleep_btn.show()
            self._wake_sleep_btn.setText("😴  SLEEP NOW" if st["awake"] else "👂  WAKE NOW")
            self._wake_sleep_btn.setStyleSheet(_off)
        else:
            self._wake_btn.setText("🎙  WAKE WORD: OFF")
            self._wake_btn.setStyleSheet(_off)
            self._wake_sleep_btn.hide()

    def _toggle_wake_word(self):
        st = self._wake_state()
        if not st["ready"]:
            # First time: download openwakeword + model in a worker thread.
            self._wake_btn.setText("⬇  DOWNLOADING… (one-time)")
            self._wake_btn.setEnabled(False)
            def _work():
                try:
                    from core.wake_word import install_and_download
                    ok, msg = install_and_download(
                        logger=lambda m: self._log_sig.emit(f"SYS: {m}"))
                except Exception as e:
                    ok, msg = False, str(e)
                if ok and self.on_wake_toggle:
                    try:
                        self.on_wake_toggle(True)   # auto-enable after a successful download
                    except Exception:
                        pass
                self._wake_dl_sig.emit(ok, msg)
            threading.Thread(target=_work, daemon=True).start()
            return
        # Already downloaded → just flip enabled/disabled through JarvisLive.
        if self.on_wake_toggle:
            try:
                self.on_wake_toggle(not st["enabled"])
            except Exception:
                pass
        self._refresh_wake_btns()

    def _on_wake_install_done(self, ok: bool, msg: str):
        self._log_sig.emit(f"SYS: {'Wake word ready.' if ok else 'Wake word setup failed: ' + msg}")
        self._refresh_wake_btns()

    def _tap_wake_manual(self):
        if self.on_wake_manual:
            try:
                self.on_wake_manual()
            except Exception:
                pass
        self._refresh_wake_btns()

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        if hasattr(self, '_settings_hub'):
            self._settings_hub.show_hub("identity")

    def _preview_ui_color(self, hex_color: str):
        """Live preview — paints the whole interface the new colour (does NOT write to config)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = "",
                           voice: str = ""):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or "JARVIS"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — {APP_VERSION}")
        self._title_lbl.setText(display)
        saved_subtitle = _read_full_config().get("hud_subtitle")
        if saved_subtitle:
            self._sub_lbl.setText(saved_subtitle)
        elif display in ("JARVIS", "J.A.R.V.I.S"):
            self._sub_lbl.setText("Just A Rather Very Intelligent System")
        else:
            self._sub_lbl.setText("Personal AI Assistant")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Live-paint the whole interface (panels, buttons, borders, HUD)
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        # Voice change → persist and, if it actually changed, rebuild the Live
        # session so the new voice takes effect (it's fixed at connect time).
        voice_changed = False
        if voice:
            from memory.config_manager import get_voice, save_voice
            if voice != get_voice():
                save_voice(voice)
                voice_changed = True

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
            if voice_changed:
                from memory.config_manager import get_voice_display_name
                self._log.append_log(f"SYS: Voice set — {get_voice_display_name(voice)}")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")
        if voice_changed and self.on_voice_change:
            self.on_voice_change()

    def _centre_overlay(self, ov) -> None:
        """Place a floating overlay in the middle of the HUD and show it."""
        cw = self.centralWidget()
        ov.adjustSize()
        ov.setGeometry(
            max(0, (cw.width()  - ov.width())  // 2),
            max(0, (cw.height() - ov.height()) // 2),
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()

    # ── Audio devices ────────────────────────────────────────────────────────

    def _open_audio_devices(self):
        if hasattr(self, '_settings_hub'):
            self._settings_hub.show_hub("audio")

    def _on_audio_devices_applied(self):
        self._log.append_log("SYS: Audio devices updated.")
        if self.on_audio_device_change:
            self.on_audio_device_change()

    # ── Memory panel ─────────────────────────────────────────────────────────

    def _open_memory_panel(self):
        if hasattr(self, '_settings_hub'):
            self._settings_hub.show_hub("memory")

    # ── Irreversible-action confirmation ─────────────────────────────────────

    def _show_confirm_banner(self, title: str, detail: str):
        self._hide_confirm_banner()
        ov = ConfirmBanner(title, detail, parent=self.centralWidget())
        ov.answered.connect(self._on_confirm_answered)
        self._centre_overlay(ov)
        self._confirm_overlay = ov

    def _hide_confirm_banner(self):
        ov = getattr(self, "_confirm_overlay", None)
        if ov is not None:
            ov.hide()
            ov.deleteLater()
            self._confirm_overlay = None

    def _on_confirm_answered(self, accepted: bool):
        # Tear the banner down first: core.confirm.resolve() may be about to
        # shut the machine down, and a live widget mid-callback is not where you
        # want to be when that happens.
        self._hide_confirm_banner()
        try:
            from core.confirm import resolve
            resolve(bool(accepted))
        except Exception as e:
            self._log.append_log(f"ERR: Confirmation failed — {e}")

    def _open_plugin_manager(self):
        if hasattr(self, '_settings_hub'):
            self._settings_hub.show_hub("plugins")

    def _open_plugin_settings(self):
        if hasattr(self, '_settings_hub'):
            self._settings_hub.show_hub("plugins")

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 6
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    # ────────────────────────────────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇")
            self._mute_btn.setToolTip("Unmute microphone")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.MUTED_C};
                    border: none; border-radius: 9px;
                }}
            """)
        else:
            self._mute_btn.setText("🔊")
            self._mute_btn.setToolTip("Mute microphone")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.GREEN};
                    border: none; border-radius: 9px;
                }}
                QPushButton:hover {{ background: #001f10; }}
            """)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _show_setup(self):
        if hasattr(self, '_settings_hub'):
            self._settings_hub.show_hub("core")

    def _on_setup_done(self, key: str, os_name: str):
        old_palette = current_palette()
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = _read_full_config()
        data["gemini_api_key"] = key
        data["os_system"] = os_name
        API_FILE.write_text(
            json.dumps(data, indent=4),
            encoding="utf-8",
        )
        apply_ui_accent(data.get("ui_color") or DEFAULT_UI_COLOR)
        retheme_all_widgets(old_palette, current_palette())
        self._ready = True
        self._api_warning.hide()
        if hasattr(self, '_settings_hub') and self._settings_hub.isVisible():
            self._settings_hub.hide_hub()
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._apply_state("LISTENING")
        self._assistant_name = _read_full_config().get("assistant_name", "JARVIS") or "JARVIS"
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._assistant_name} online.")


    def _start_startup_voice_unlock(self):
        if getattr(self, "_startup_voice_busy", False): return
        try:
            list_challenges, _, _, _, get_challenge, verify_challenge_answer = self._voice_lock_modules()
            challenges = list_challenges()
            if not challenges:
                self._startup_status_lbl.setText("No voice challenge configured. Use Master PIN to set one in Settings.")
                return
            challenge = random.choice(challenges)
            full = get_challenge(challenge["id"])
            if not full: return
            self._startup_voice_busy = True
            self._startup_voice_challenge_id = challenge["id"]
            self._startup_voice_answer_verifier = verify_challenge_answer
            if getattr(self, "_startup_question_lbl", None): self._startup_question_lbl.setText(f"❓ {full['question']}")
            self._startup_mic_btn.setEnabled(False); self._startup_mic_btn.setText("🎙️  LISTENING…")
            self._startup_status_lbl.setStyleSheet(f"color:{C.GREEN}; background:transparent;")
            self._startup_status_lbl.setText("Answer the question aloud…")
        except Exception as exc:
            self._startup_voice_busy = False; self._startup_status_lbl.setText(f"Voice challenge unavailable: {exc}"); return

        def worker():
            try:
                text = _record_voice_phrase()
                ok = bool(text) and bool(verify_challenge_answer(self._startup_voice_challenge_id, text))
                self._startup_voice_sig.emit(ok, text or "No speech detected.")
            except Exception as exc:
                self._startup_voice_sig.emit(False, f"ERROR: {exc}")
        threading.Thread(target=worker, daemon=True, name="startup-voice-challenge").start()

    def _on_startup_voice_result(self, ok: bool, text: str):
        self._startup_voice_busy = False
        if getattr(self, "_startup_mic_btn", None):
            self._startup_mic_btn.setEnabled(True); self._startup_mic_btn.setText("🎙️  VOICE UNLOCK")
        if getattr(self, "_startup_status_lbl", None):
            if ok:
                self._startup_status_lbl.setStyleSheet(f"color:{C.GREEN}; background:transparent;")
                self._startup_status_lbl.setText("Challenge accepted — unlocking JARVIS…")
                pending = getattr(self, "_startup_pin_pending", None)
                if pending is not None:
                    pending["value"] = {"method":"voice", "value":text}; pending["event"].set()
                if self._startup_dialog is not None: self._startup_dialog.accept()
            else:
                self._startup_status_lbl.setStyleSheet(f"color:{C.RED}; background:transparent;")
                self._startup_status_lbl.setText("Wrong answer. Access denied." if text and not text.startswith("ERROR:") else (text or "No speech detected."))

    def _show_startup_pin_dialog(self):
        """Show the mandatory startup Master PIN dialog on the Qt GUI thread.

        The asyncio runner lives in a worker thread, so it must never create a
        Qt dialog directly. request_startup_pin() waits on an Event while this
        signal creates the modal dialog here on the GUI thread.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("JARVIS — AUTHENTICATION REQUIRED")
        dlg.setModal(True)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumWidth(390)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: {C.BG};
                color: {C.TEXT};
            }}
            QLabel {{
                color: {C.TEXT};
                font-family: {UI_FONT};
            }}
            QLineEdit {{
                background: {C.PANEL2};
                color: {C.WHITE};
                border: 1px solid {C.BORDER_B};
                border-radius: 5px;
                padding: 10px;
                font-size: 18px;
                letter-spacing: 4px;
            }}
            QPushButton {{
                background: {C.PANEL2};
                color: {C.PRI};
                border: 1px solid {C.BORDER_B};
                border-radius: 5px;
                padding: 8px 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {C.PRI_GHO};
                border-color: {C.PRI};
            }}
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("🔐  JARVIS SECURITY")
        title.setFont(QFont(UI_FONT, 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI};")
        layout.addWidget(title)

        subtitle = QLabel("Master PIN required to unlock JARVIS")
        subtitle.setStyleSheet(f"color: {C.TEXT_MED};")
        layout.addWidget(subtitle)

        pin = QLineEdit()
        pin.setPlaceholderText("Enter Master PIN")
        pin.setEchoMode(QLineEdit.EchoMode.Password)
        pin.setMaxLength(12)
        pin.setInputMethodHints(Qt.InputMethodHint.ImhDigitsOnly)
        layout.addWidget(pin)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        unlock = QPushButton("UNLOCK")
        cancel = QPushButton("CANCEL")
        buttons.addWidget(cancel)
        buttons.addWidget(unlock)
        layout.addLayout(buttons)

        result = {"value": None}

        self._startup_voice_busy = False
        self._startup_voice_challenge_id = None
        question_lbl = QLabel("No matching face detected. Enter your Master PIN to continue.")
        question_lbl.setWordWrap(True)
        question_lbl.setStyleSheet(f"color: {C.TEXT}; background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 6px; padding: 10px;")
        layout.addWidget(question_lbl)
        self._startup_question_lbl = question_lbl

        status_lbl = QLabel("Face not recognized — enter your Master PIN.")
        status_lbl.setWordWrap(True)
        status_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        layout.addWidget(status_lbl)

        mic_btn = QPushButton("🎙️  VOICE UNLOCK")
        mic_btn.setToolTip("Answer the displayed local voice challenge")
        mic_btn.clicked.connect(self._start_startup_voice_unlock)
        # Startup access is limited to an enrolled face or the Master PIN.
        mic_btn.hide()
        question_lbl.hide()
        layout.addWidget(mic_btn)

        def accept_pin():
            value = pin.text().strip()
            if not value:
                pin.setFocus()
                return
            try:
                from plugins._face_security import get_face_security
                security = get_face_security()
                if not security.verify_pin(value):
                    status_lbl.setText("Invalid Master PIN. Please try again.")
                    status_lbl.setStyleSheet(f"color: {C.RED}; background: transparent;")
                    pin.selectAll()
                    pin.setFocus()
                    return
            except Exception as exc:
                status_lbl.setText(f"PIN verification error: {exc}")
                status_lbl.setStyleSheet(f"color: {C.RED}; background: transparent;")
                return
            result["value"] = {"method": "pin", "value": value}
            pending = getattr(self, "_startup_pin_pending", None)
            if pending is not None:
                pending["value"] = result["value"]
                pending["event"].set()
            dlg.accept()

        unlock.clicked.connect(accept_pin)
        pin.returnPressed.connect(accept_pin)
        cancel.clicked.connect(dlg.reject)
        self._startup_dialog = dlg
        self._startup_mic_btn = mic_btn
        self._startup_status_lbl = status_lbl
        pin.setFocus()
        dlg.exec()
        self._startup_dialog = None
        self._startup_mic_btn = None
        self._startup_status_lbl = None
        self._startup_question_lbl = None
        self._startup_voice_challenge_id = None

        # Fallback: if dialog was closed without accept (X button / cancel),
        # ensure the runner thread is unblocked
        pending = getattr(self, "_startup_pin_pending", None)
        if pending is not None and not pending["event"].is_set():
            pending["value"] = result["value"]  # None = cancelled
            pending["event"].set()


class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class JarvisUI:
    def __init__(self, face_path: str, size=None):
        # ── Windows taskbar identity ──────────────────────────────────────────
        # Set the AppUserModelID BEFORE creating QApplication so Windows
        # associates the running process with the correct icon in the taskbar.
        # Without this, Windows groups the process under python.exe and shows
        # the Python icon instead of the JARVIS icon.
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "JARVIS.App.1"
                )
            except Exception:
                pass

        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        if APP_ICON.is_file():
            self._app.setWindowIcon(QIcon(str(APP_ICON)))
        self._win = MainWindow(face_path)
        self.root = _RootShim(self._app)
        self._win.show()
        self._win.raise_()
        self._win.activateWindow()

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def on_voice_change(self):
        return self._win.on_voice_change

    @on_voice_change.setter
    def on_voice_change(self, cb):
        self._win.on_voice_change = cb

    @property
    def on_audio_device_change(self):
        return self._win.on_audio_device_change

    @on_audio_device_change.setter
    def on_audio_device_change(self, cb):
        self._win.on_audio_device_change = cb

    def show_confirm(self, title: str, detail: str) -> None:
        """Thread-safe: raise the irreversible-action gate. Called from action
        handlers running in executor threads, so it goes through a signal."""
        self._win._confirm_sig.emit(str(title)[:120], str(detail)[:300])

    def hide_confirm(self) -> None:
        """Thread-safe: take the gate down."""
        self._win._confirm_hide_sig.emit()

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    @property
    def get_plugin_settings(self):
        return self._win.get_plugin_settings

    @get_plugin_settings.setter
    def get_plugin_settings(self, cb):
        self._win.get_plugin_settings = cb

    @property
    def on_wake_toggle(self):
        return self._win.on_wake_toggle

    @on_wake_toggle.setter
    def on_wake_toggle(self, cb):
        self._win.on_wake_toggle = cb

    @property
    def on_wake_manual(self):
        return self._win.on_wake_manual

    @on_wake_manual.setter
    def on_wake_manual(self, cb):
        self._win.on_wake_manual = cb

    @property
    def wake_get_state(self):
        return self._win.wake_get_state

    @wake_get_state.setter
    def wake_get_state(self, cb):
        self._win.wake_get_state = cb

    def set_audio_level(self, level: float) -> None:
        """Thread-safe: feed a 0.0–1.0 live audio level to the HUD waveform.
        Called from the audio threads; a plain float store is atomic under the
        GIL, so no signal/lock is needed for this cosmetic value."""
        try:
            self._win.hud.set_audio_level(level)
        except Exception:
            pass

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def request_startup_pin(self):
        """Thread-safe blocking request for the startup Master PIN.

        Called from the asyncio worker thread. The actual dialog is created on
        the Qt GUI thread through _startup_pin_sig, then this thread waits until
        the user submits or cancels it.
        """
        event = threading.Event()
        pending = {"event": event, "value": None}
        self._win._startup_pin_pending = pending
        self._win._startup_pin_sig.emit()
        event.wait()
        self._win._startup_pin_pending = None
        return pending["value"]

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def show_location(self, place: str = ""):
        """Thread-safe: open the in-app globe and locate or navigate."""
        self._win.show_location(place)

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")
