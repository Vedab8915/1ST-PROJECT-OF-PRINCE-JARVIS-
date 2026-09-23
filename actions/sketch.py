"""Create a clean, offline-viewable SVG sketch from a short description."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import webbrowser
from pathlib import Path

from core.gemini import SMART, text as gemini_text


def sketch(parameters: dict | None = None) -> str:
    p = parameters or {}
    concept = str(p.get("description", "")).strip()
    if not concept:
        return "Describe the sketch you want."
    prompt = (
        "Draw the user's requested subject as a complete, polished, recognizable vector illustration. "
        "Follow every requested object, action, composition, style, and label; do not replace the request "
        "with a generic icon. Use clean deliberate shapes, balanced spacing, readable labels, and a "
        "light neutral background. Return exactly one complete SVG document with xmlns=\"http://www.w3.org/2000/svg\", "
        "width=\"900\", height=\"600\", and viewBox=\"0 0 900 600\". SVG markup only, no markdown or prose. "
        "Do not include scripts, links, foreignObject, external images, animation, or event handlers. Keep it under 20 KB.\n"
        f"Exact drawing request: {concept[:1500]}"
    )
    svg = gemini_text(prompt, tier=SMART, timeout_ms=30000, default="")
    svg = re.sub(r"^```(?:svg|xml)?\s*|\s*```$", "", svg.strip(), flags=re.I)
    match = re.search(r"<svg\b[\s\S]*?</svg\s*>", svg, flags=re.I)
    if match:
        svg = match.group(0)
    if not svg or len(svg.encode("utf-8")) > 25_000:
        return "I could not generate a usable sketch. Try a shorter description."
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return "The sketch generator returned invalid SVG. Try again with a simpler subject."
    if root.tag.split("}")[-1].lower() != "svg":
        return "The sketch generator did not return an SVG image."
    root.set("xmlns", "http://www.w3.org/2000/svg")
    root.set("width", root.get("width") or "900")
    root.set("height", root.get("height") or "600")
    root.set("viewBox", root.get("viewBox") or "0 0 900 600")
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
    try:
        opened = webbrowser.open(target.as_uri())
    except Exception:
        opened = False
    state = "and opened it for preview" if opened else "(preview could not be opened automatically)"
    return f"Created sketch {state}: {target}"


TOOL = {
    "name": "create_sketch",
    "description": "MUST use this for any request to draw or sketch an illustration, concept, icon, or diagram from a description. Include the user's full subject, requested details, style, and labels in description. It generates an SVG, saves it, and opens a preview; do not claim a drawing was made without calling this tool.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"description": {"type": "STRING", "description": "What to draw; include desired style or labels."}},
        "required": ["description"],
    },
    "handler": sketch,
}
