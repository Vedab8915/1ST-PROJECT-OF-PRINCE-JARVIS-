"""Read battery, host identity, and hardware specifications without shelling out."""
from __future__ import annotations

import platform
import socket
from pathlib import Path

import psutil


def _bytes(value: int) -> str:
    return f"{value / (1024 ** 3):.1f} GB"


def system_info(parameters: dict | None = None) -> str:
    p = parameters or {}
    detail = str(p.get("detail", "all")).lower().strip()
    rows: list[str] = []

    if detail in ("all", "battery", "power"):
        battery = psutil.sensors_battery()
        if battery is None:
            rows.append("Battery: unavailable (desktop or battery sensor not exposed)")
        else:
            state = "charging" if battery.power_plugged else "on battery"
            remaining = "unknown" if battery.secsleft < 0 else f"{battery.secsleft // 3600}h {(battery.secsleft % 3600) // 60}m remaining"
            rows.append(f"Battery: {battery.percent:.0f}%, {state}, {remaining}")

    if detail in ("all", "system", "specs", "computer"):
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage(Path.home().anchor or "/")
        rows.extend([
            f"Computer name: {socket.gethostname()}",
            f"Manufacturer/model: {_computer_model()}",
            f"Operating system: {platform.system()} {platform.release()} ({platform.version()})",
            f"Architecture: {platform.machine()}",
            f"Processor: {platform.processor() or 'name unavailable'}; {psutil.cpu_count(logical=False) or '?'} cores / {psutil.cpu_count(logical=True) or '?'} threads",
            f"Memory: {_bytes(vm.total)} RAM",
            f"System drive: {_bytes(disk.free)} free of {_bytes(disk.total)}",
            f"Python: {platform.python_version()}",
        ])
        gpu = _gpu_name()
        if gpu:
            rows.append(f"Graphics: {gpu}")

    if not rows:
        return "Choose detail: all, battery, or system."
    return "\n".join(rows)


def _computer_model() -> str:
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS")
            maker = winreg.QueryValueEx(key, "SystemManufacturer")[0].strip()
            model = winreg.QueryValueEx(key, "SystemProductName")[0].strip()
            return " ".join(x for x in (maker, model) if x and "to be filled" not in x.lower()) or "unavailable"
        except Exception:
            pass
    return "unavailable"


def _gpu_name() -> str:
    if platform.system() == "Windows":
        try:
            import wmi  # Optional; available on some installations.
            names = [x.Name.strip() for x in wmi.WMI().Win32_VideoController() if x.Name]
            return ", ".join(dict.fromkeys(names))
        except Exception:
            return ""
    return ""


TOOL = {
    "name": "system_info",
    "description": "On explicit user request only, reads real values from this computer: battery/charging, host name, OS, processor, RAM, storage, and available graphics adapter. Use for 'my PC specs', 'what computer/system is this', or battery questions. Never invent missing values: report unavailable fields as unavailable.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"detail": {"type": "STRING", "description": "all (default) | battery | system"}},
        "required": [],
    },
    "handler": system_info,
}
