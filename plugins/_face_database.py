"""Small JSON store for locally enrolled face descriptors."""
from __future__ import annotations

import json
import uuid
from pathlib import Path


class FaceDatabase:
    def __init__(self):
        self.path = Path(__file__).resolve().parent.parent / "config" / "authorized_faces.json"

    def _read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError, TypeError):
            return []

    def _write(self, faces: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(faces, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def get_faces(self) -> list[dict]:
        return [{k: v for k, v in f.items() if k != "embedding"} for f in self._read()]

    def get_face_embeddings(self) -> list[dict]:
        return [{"face_id": f["face_id"], "embedding": f["embedding"]} for f in self._read()]

    def get_face(self, face_id) -> dict | None:
        return next((f for f in self.get_faces() if f.get("face_id") == face_id), None)

    def add_face(self, name: str, embedding) -> str:
        faces = self._read()
        face_id = uuid.uuid4().hex
        faces.append({"face_id": face_id, "face_number": len(faces) + 1,
                      "name": name.strip(), "embedding": list(embedding)})
        self._write(faces)
        return face_id

    def rename_face(self, face_id, name: str) -> None:
        faces = self._read()
        for face in faces:
            if face.get("face_id") == face_id:
                face["name"] = name.strip()
                self._write(faces)
                return
        raise KeyError("Authorized face not found.")

    def remove_face(self, face_id) -> None:
        faces = [f for f in self._read() if f.get("face_id") != face_id]
        for idx, face in enumerate(faces, 1):
            face["face_number"] = idx
        self._write(faces)


_instance = None


def get_face_database() -> FaceDatabase:
    global _instance
    if _instance is None:
        _instance = FaceDatabase()
    return _instance
