"""Small cross-platform helpers shared by actions."""
from __future__ import annotations

import platform


def get_os() -> str:
    """Return a normalized operating-system name."""
    name = platform.system().lower()
    if name == "windows":
        return "windows"
    if name == "darwin":
        return "mac"
    if name == "linux":
        return "linux"
    return name or "unknown"


def is_windows() -> bool:
    return get_os() == "windows"


def is_mac() -> bool:
    return get_os() == "mac"


def is_linux() -> bool:
    return get_os() == "linux"
