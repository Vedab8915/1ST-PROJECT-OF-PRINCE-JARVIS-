"""Create editable PowerPoint decks from an AI-generated slide outline."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

PLUGIN = {
    "name": "create_presentation",
    "description": (
        "Create an editable PowerPoint for a topic the user gives. Generate the "
        "slide content yourself before calling this tool: use a clear story, "
        "6–10 content slides unless the user asks for a different length, concise "
        "bullets, a useful takeaway and visual idea for each slide, and include a "
        "sources list for factual or current claims. The tool formats and saves "
        "the supplied outline as a polished widescreen .pptx in downloads/presentations. "
        "Do not call until you have a complete slide outline."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "topic": {"type": "STRING", "description": "The presentation topic."},
            "title": {"type": "STRING", "description": "Cover slide title."},
            "subtitle": {"type": "STRING", "description": "Short cover slide subtitle."},
            "slides": {
                "type": "ARRAY",
                "description": "Ordered content slides, excluding the cover and optional sources slide.",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "title": {"type": "STRING"},
                        "bullets": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "description": "Two to five concise points.",
                        },
                        "takeaway": {"type": "STRING", "description": "One key takeaway for this slide."},
                        "visual_idea": {"type": "STRING", "description": "A simple visual or example to show."},
                    },
                    "required": ["title", "bullets"],
                },
            },
            "sources": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Source titles and URLs for factual claims, if applicable.",
            },
        },
        "required": ["topic", "title", "slides"],
    },
}

_ROOT = Path(__file__).resolve().parent.parent
_NAVY = (13, 27, 47)
_BLUE = (28, 87, 130)
_TEAL = (0, 176, 170)
_INK = (34, 48, 66)
_MUTED = (91, 108, 126)
_PAPER = (247, 249, 252)
_WHITE = (255, 255, 255)


def _rgb(rgb):
    from pptx.dml.color import RGBColor
    return RGBColor(*rgb)


def _add_box(slide, x, y, w, h, color, rounded=False):
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color)
    shape.line.fill.background()
    return shape


def _add_text(slide, text, x, y, w, h, size, color, bold=False, font="Aptos"):
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Inches, Pt
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(0.02)
    frame.margin_right = Inches(0.02)
    frame.margin_top = Inches(0.01)
    frame.margin_bottom = Inches(0.01)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.LEFT
    run = paragraph.add_run()
    run.text = str(text)
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = _rgb(color)
    return shape


def _set_bullet(paragraph):
    from pptx.oxml.xmlchemy import OxmlElement
    ppr = paragraph._p.get_or_add_pPr()
    bullet = OxmlElement("a:buChar")
    bullet.set("char", "•")
    ppr.append(bullet)


def _content_slide(prs, item, index, total):
    from pptx.util import Inches, Pt
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = _rgb(_PAPER)
    _add_box(slide, 0, 0, 13.333, 0.12, _TEAL)
    _add_text(slide, "JARVIS  /  PRESENTATION", 0.62, 0.32, 5.5, 0.25, 9, _BLUE, True)
    title = str(item.get("title") or f"Section {index}").strip()[:120]
    _add_text(slide, title, 0.62, 0.78, 12.05, 0.78, 27, _NAVY, True)
    _add_box(slide, 0.64, 1.58, 0.78, 0.055, _TEAL)

    bullets = item.get("bullets") or []
    if not isinstance(bullets, list):
        bullets = [str(bullets)]
    bullets = [str(text).strip()[:400] for text in bullets if str(text).strip()][:5]
    bullets = bullets or ["Key information for this section."]
    body = slide.shapes.add_textbox(Inches(0.75), Inches(1.95), Inches(7.15), Inches(4.62))
    frame = body.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = Inches(0.02)
    frame.margin_right = Inches(0.15)
    for i, text in enumerate(bullets):
        paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        paragraph.text = text
        paragraph.level = 0
        _set_bullet(paragraph)
        paragraph.space_after = Pt(17)
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(19)
        paragraph.font.color.rgb = _rgb(_INK)

    _add_box(slide, 8.32, 2.00, 4.35, 4.30, _WHITE, rounded=True)
    _add_box(slide, 8.32, 2.00, 0.09, 4.30, _TEAL)
    visual = str(item.get("visual_idea") or "Use a simple diagram or real-world example.").strip()[:280]
    takeaway = str(item.get("takeaway") or "Remember the main point from this section.").strip()[:280]
    _add_text(slide, "VISUAL IDEA", 8.72, 2.34, 3.45, 0.30, 10, _TEAL, True)
    _add_text(slide, visual, 8.72, 2.76, 3.45, 1.04, 16, _INK, True)
    _add_box(slide, 8.72, 4.05, 3.45, 0.025, (221, 230, 238))
    _add_text(slide, "KEY TAKEAWAY", 8.72, 4.32, 3.45, 0.30, 10, _BLUE, True)
    _add_text(slide, takeaway, 8.72, 4.72, 3.45, 1.18, 15, _MUTED)
    _add_text(slide, f"{index:02d}  /  {total:02d}", 11.30, 6.95, 1.35, 0.24, 9, _MUTED)
    return slide


def _cover(prs, title, subtitle, topic):
    from pptx.util import Inches
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_NAVY)
    _add_box(slide, 0.86, 1.07, 0.12, 4.9, _TEAL)
    _add_text(slide, "JARVIS  /  PRESENTATION", 1.32, 1.20, 7.0, 0.35, 11, (134, 220, 220), True)
    _add_text(slide, str(title).strip()[:120] or str(topic).strip()[:120],
              1.30, 2.05, 10.65, 1.95, 34, _WHITE, True)
    _add_text(slide, str(subtitle or topic).strip()[:220],
              1.34, 4.25, 9.7, 0.98, 20, (204, 218, 230))
    _add_box(slide, 1.34, 5.75, 1.08, 0.06, _TEAL)
    return slide


def _sources_slide(prs, sources):
    from pptx.util import Inches, Pt
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _PAPER
    _add_box(slide, 0, 0, 13.333, 0.12, _TEAL)
    _add_text(slide, "SOURCES", 0.72, 0.62, 10, 0.7, 28, _NAVY, True)
    _add_box(slide, 0.74, 1.40, 0.78, 0.055, _TEAL)
    body = slide.shapes.add_textbox(Inches(0.82), Inches(1.82), Inches(11.7), Inches(4.9))
    frame = body.text_frame
    frame.clear()
    frame.word_wrap = True
    for i, source in enumerate(sources[:20]):
        paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        paragraph.text = str(source).strip()[:500]
        paragraph.space_after = Pt(12)
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(14)
        paragraph.font.color.rgb = _rgb(_INK)
    return slide


def run(parameters: dict) -> str:
    try:
        from pptx import Presentation
        from pptx.util import Inches
    except ImportError as exc:
        return f"PowerPoint generation needs python-pptx: {exc}"

    params = parameters or {}
    topic = str(params.get("topic") or "").strip()
    title = str(params.get("title") or topic).strip()
    slides = params.get("slides")
    if not topic or not title:
        return "Please provide a topic and presentation title."
    if not isinstance(slides, list) or not 2 <= len(slides) <= 20:
        return "Please prepare between 2 and 20 content slides before creating the deck."

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = title[:200]
    prs.core_properties.subject = topic[:500]
    prs.core_properties.author = "JARVIS"

    _cover(prs, title, params.get("subtitle", ""), topic)
    for number, item in enumerate(slides, 1):
        if not isinstance(item, dict):
            return f"Slide {number} is invalid; each slide needs a title and bullet list."
        if not str(item.get("title") or "").strip():
            return f"Slide {number} is missing a title."
        _content_slide(prs, item, number, len(slides))

    sources = params.get("sources") or []
    if isinstance(sources, list) and sources:
        _sources_slide(prs, sources)

    folder = _ROOT / "downloads" / "presentations"
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", topic).strip("_").lower()[:48] or "jarvis_presentation"
    target = folder / f"{slug}_{datetime.now():%Y%m%d_%H%M%S}.pptx"
    prs.save(target)
    return f"Presentation ready: {target} ({len(prs.slides)} slides)."
