"""Create a clean, offline-viewable SVG sketch from a short description."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from core.gemini import text as gemini_text


def sketch(parameters: dict | None = None) -> str:
    p = parameters or {}
    concept = str(p.get("description", "")).strip()
    if not concept:
        return "Describe the sketch you want."
    prompt = (
        "Create a simple polished vector illustration as raw SVG only. Use a 900x600 viewBox, "
        "clear shapes and a light background. No markdown. Do not include scripts, links, "
        "foreignObject, external images, animation, or event handlers. Keep it under 20 KB.\n"
        f"Sketch request: {concept[:1000]}"
    )
    svg = gemini_text(prompt, default="")
    svg = re.sub(r"^```(?:svg|xml)?\s*|\s*```$", "", svg.strip(), flags=re.I)
    if not svg or len(svg.encode("utf-8")) > 25_000:
        return "I could not generate a usable sketch. Try a shorter description."
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return "The sketch generator returned invalid SVG. Try again with a simpler subject."
    if root.tag.split("}")[-1].lower() != "svg":
        return "The sketch generator did not return an SVG image."
    forbidden = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video"}
    for parent in root.iter():
        if parent.tag.split("}")[-1].lower() in forbidden:
            return "The generated sketch contained unsupported content and was discarded."
        for attr, value in parent.attrib.items():
            key = attr.split("}")[-1].lower()
            if key.startswith("on") or (key in {"href", "src"} and not value.startswith("#")):
                return "The generated sketch contained an external reference and was discarded."
            if "javascript:" in value.lower() or "data:" in value.lower():
                return "The generated sketch contained an unsafe reference and was discarded."

    target_dir = Path(__file__).resolve().parents[1] / "downloads" / "sketches"
    target_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", concept.lower()).strip("-")[:48] or "sketch"
    target = target_dir / f"{slug}.svg"
    if target.exists():
        from datetime import datetime
        target = target_dir / f"{slug}-{datetime.now():%Y%m%d-%H%M%S}.svg"
    target.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
    return f"Created sketch: {target}"


TOOL = {
    "name": "create_sketch",
    "description": "Creates a simple vector sketch/illustration from the user's description and saves an SVG in downloads/sketches. Use for requests to draw or sketch a concept, diagram, icon, or simple illustration.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"description": {"type": "STRING", "description": "What to draw; include desired style or labels."}},
        "required": ["description"],
    },
    "handler": sketch,
}
