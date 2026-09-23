"""Local Master PIN verification backed by a salted PBKDF2 hash."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path


_CONFIG = Path(__file__).resolve().parent.parent / "config" / "master_pin.json"
_DEFAULT_PIN = "298422"
_ITERATIONS = 310_000


class FaceSecurity:
    def __init__(self, path: Path = _CONFIG):
        self.path = path

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("salt") and data.get("hash"):
                return data
        except (OSError, ValueError, TypeError):
            pass
        return self._write(_DEFAULT_PIN)

    def _write(self, pin: str) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _ITERATIONS)
        data = {"salt": salt.hex(), "hash": digest.hex(), "iterations": _ITERATIONS}
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temp, self.path)
        return data

    def verify_pin(self, pin: str) -> bool:
        if not isinstance(pin, str) or not re.fullmatch(r"\d{4,12}", pin):
            return False
        data = self._read()
        try:
            digest = hashlib.pbkdf2_hmac(
                "sha256", pin.encode("utf-8"), bytes.fromhex(data["salt"]),
                int(data.get("iterations", _ITERATIONS)),
            ).hex()
            return hmac.compare_digest(digest, data["hash"])
        except (KeyError, ValueError, TypeError):
            return False

    def change_pin(self, current: str, new: str) -> bool:
        if not self.verify_pin(current):
            return False
        if not isinstance(new, str) or not re.fullmatch(r"\d{4,12}", new):
            raise ValueError("PIN must contain 4 to 12 digits.")
        self._write(new)
        return True


_instance = None


def get_face_security() -> FaceSecurity:
    global _instance
    if _instance is None:
        _instance = FaceSecurity()
    return _instance
