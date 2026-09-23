"""Startup authentication using enrolled face descriptors."""
from __future__ import annotations

from ._face_database import get_face_database
from ._face_recognizer import get_face_recognizer


class FaceAuthManager:
    def __init__(self):
        self.recognizer = get_face_recognizer()
        self.database = get_face_database()

    def verify_once(self, threshold: float = .78) -> dict:
        faces = self.database.get_face_embeddings()
        if not faces:
            return {"success": False, "reason": "NO_ENROLLED_FACES",
                    "message": "No authorized face is enrolled."}
        camera = self.recognizer._camera()
        if camera is None:
            return {"success": False, "reason": "NO_CAMERA", "message": "Camera unavailable."}
        ok, frame = camera.read()
        if not ok:
            return {"success": False, "reason": "NO_FRAME", "message": "Camera frame unavailable."}
        descriptor = self.recognizer._embedding(frame)
        if descriptor is None:
            return {"success": False, "reason": "NO_FACE", "message": "No face detected."}
        match = self.recognizer.find_best_match(descriptor, faces, threshold)
        if not match or match["similarity"] < threshold:
            return {"success": False, "reason": "UNKNOWN_FACE", "similarity": match["similarity"] if match else 0,
                    "message": "Face is not authorized."}
        face = self.database.get_face(match["face_id"])
        return {"success": True, "reason": "MATCH", "face_name": (face or {}).get("name"),
                "face_id": match["face_id"], "similarity": match["similarity"]}


_instance = None


def get_face_auth_manager() -> FaceAuthManager:
    global _instance
    if _instance is None:
        _instance = FaceAuthManager()
    return _instance
