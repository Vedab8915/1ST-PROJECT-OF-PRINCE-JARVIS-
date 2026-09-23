"""OpenCV frontal-face capture and compact local appearance descriptors."""
from __future__ import annotations

import time

import cv2
import numpy as np


class FaceRecognizer:
    def __init__(self):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.cascade = cv2.CascadeClassifier(cascade_path)
        self.camera = None

    def _camera(self):
        if self.camera is None or not self.camera.isOpened():
            self.camera = cv2.VideoCapture(0)
            if not self.camera.isOpened():
                self.close_camera()
                return None
        return self.camera

    def _embedding(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.cascade.detectMultiScale(gray, 1.15, 5, minSize=(90, 90))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
        pad_x, pad_y = int(w * .12), int(h * .12)
        crop = gray[max(0, y-pad_y):min(gray.shape[0], y+h+pad_y),
                    max(0, x-pad_x):min(gray.shape[1], x+w+pad_x)]
        crop = cv2.resize(crop, (96, 96), interpolation=cv2.INTER_AREA)
        crop = cv2.equalizeHist(crop)
        # Local binary pattern histogram is less sensitive to brightness than raw pixels.
        c = crop[1:-1, 1:-1]
        neighbors = (crop[:-2, :-2], crop[:-2, 1:-1], crop[:-2, 2:],
                     crop[1:-1, 2:], crop[2:, 2:], crop[2:, 1:-1],
                     crop[2:, :-2], crop[1:-1, :-2])
        lbp = np.zeros(c.shape, dtype=np.uint8)
        for bit, neighbor in enumerate(neighbors):
            lbp |= ((neighbor >= c).astype(np.uint8) << bit)
        hist = cv2.calcHist([lbp], [0], None, [256], [0, 256]).reshape(-1)
        hist /= max(float(hist.sum()), 1.0)
        return hist.astype(float).tolist()

    def capture_face_samples(self, sample_count: int = 5):
        samples = []
        deadline = time.monotonic() + 12
        try:
            while len(samples) < sample_count and time.monotonic() < deadline:
                camera = self._camera()
                if camera is None:
                    break
                ok, frame = camera.read()
                if ok:
                    descriptor = self._embedding(frame)
                    if descriptor is not None:
                        samples.append(descriptor)
                        time.sleep(.15)
                else:
                    time.sleep(.1)
        finally:
            self.close_camera()
        return samples

    @staticmethod
    def average_embeddings(samples):
        if not samples:
            return None
        vector = np.mean(np.asarray(samples, dtype=float), axis=0)
        total = float(vector.sum())
        return (vector / total).tolist() if total else None

    @staticmethod
    def find_best_match(embedding, known_faces, threshold=.45):
        probe = np.asarray(embedding, dtype=float)
        best = None
        for item in known_faces:
            try:
                known = np.asarray(item["embedding"], dtype=float)
                similarity = float(np.minimum(probe, known).sum())
            except (KeyError, TypeError, ValueError):
                continue
            if best is None or similarity > best["similarity"]:
                best = {"face_id": item["face_id"], "similarity": similarity}
        return best if best and best["similarity"] >= threshold else best

    def close_camera(self):
        camera, self.camera = self.camera, None
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass


_instance = None


def get_face_recognizer() -> FaceRecognizer:
    global _instance
    if _instance is None:
        _instance = FaceRecognizer()
    return _instance
