"""Save feedback the user explicitly asks Jarvis to record."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def save_feedback(parameters: dict | None = None) -> str:
    p = parameters or {}
    feedback = str(p.get("feedback", "")).strip()
    if not feedback:
        return "Tell me the feedback you want recorded."
    rating = str(p.get("rating", "")).strip().lower()
    if rating and rating not in {"positive", "negative", "suggestion", "bug"}:
        rating = ""
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), "rating": rating, "feedback": feedback[:4000]}
    target = Path(__file__).resolve().parents[1] / "memory" / "feedback.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return "Feedback saved locally. It is recorded for review; Jarvis does not automatically retrain from it."


TOOL = {
    "name": "save_feedback",
    "description": "Records feedback or a bug report about Jarvis only when the user explicitly asks to save/send/remember that feedback. Stores it locally in memory/feedback.jsonl; it does not claim that the model learns automatically.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "feedback": {"type": "STRING", "description": "The user's feedback or bug report."},
            "rating": {"type": "STRING", "description": "positive | negative | suggestion | bug; optional"},
        },
        "required": ["feedback"],
    },
    "handler": save_feedback,
}
