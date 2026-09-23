"""Create editable PowerPoint decks from an AI-generated slide outline."""
from __future__ import annotations

import re
import html
import io
import concurrent.futures
from datetime import datetime
from pathlib import Path

PLUGIN = {
    "name": "create_presentation",
    "description": (
        "MUST be used for every request to make/create/build a PowerPoint or PPT. "
        "Pass the topic immediately; the tool creates the slide outline when one is not supplied. "
        "Use a clear story, "
        "6–10 content slides unless the user asks for a different length, concise "
        "bullets, a useful takeaway and specific visual idea for each slide, and include a "
        "sources list for factual or current claims. The tool finds and embeds relevant, "
        "openly licensed Wikimedia Commons photographs for the slides and adds image credits. "
        "It formats and saves "
        "the supplied outline as a polished widescreen .pptx in downloads/presentations. "
        "Do not call until you have a complete slide outline."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "topic": {"type": "STRING", "description": "The presentation topic."},
            "title": {"type": "STRING", "description": "Cover slide title."},
            "subtitle": {"type": "STRING", "description": "Short cover slide subtitle."},
            "audience": {"type": "STRING", "description": "Intended audience, if the user specified one."},
            "style": {"type": "STRING", "description": "Visual/tone direction such as executive, academic, or classroom."},
            "slide_count": {"type": "INTEGER", "description": "Requested content slide count; defaults to 8."},
            "requirements": {"type": "STRING", "description": "Extra user requirements to follow."},
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
        "required": ["topic"],
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


def _content_slide(prs, item, index, total, image=None):
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
    if image:
        from pptx.util import Inches
        slide.shapes.add_picture(image["stream"], Inches(8.41), Inches(2.08), Inches(4.17), Inches(2.35))
        _add_text(slide, "VISUAL IDEA", 8.65, 4.58, 3.62, 0.22, 9, _TEAL, True)
        _add_text(slide, visual, 8.65, 4.84, 3.62, 0.54, 12, _INK, True)
        _add_box(slide, 8.65, 5.46, 3.62, 0.025, (221, 230, 238))
        _add_text(slide, "KEY TAKEAWAY", 8.65, 5.59, 1.55, 0.20, 8, _BLUE, True)
        _add_text(slide, takeaway, 10.15, 5.56, 2.10, 0.48, 10, _MUTED)
        _add_text(slide, image["credit"], 8.65, 6.10, 3.62, 0.14, 6, _MUTED)
    else:
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


def _sources_slide(prs, sources, page=1, pages=1):
    from pptx.util import Inches, Pt
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(_PAPER)
    _add_box(slide, 0, 0, 13.333, 0.12, _TEAL)
    heading = "SOURCES & IMAGE CREDITS" if pages == 1 else f"SOURCES & IMAGE CREDITS  {page}/{pages}"
    _add_text(slide, heading, 0.72, 0.62, 11.7, 0.7, 25, _NAVY, True)
    _add_box(slide, 0.74, 1.40, 0.78, 0.055, _TEAL)
    body = slide.shapes.add_textbox(Inches(0.82), Inches(1.82), Inches(11.7), Inches(4.9))
    frame = body.text_frame
    frame.clear()
    frame.word_wrap = True
    for i, source in enumerate(sources):
        paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        paragraph.text = str(source).strip()[:500]
        paragraph.space_after = Pt(12)
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(14)
        paragraph.font.color.rgb = _rgb(_INK)
    return slide


def _plain(value: str, limit: int = 180) -> str:
    value = re.sub(r"<[^>]*>", " ", html.unescape(str(value or "")))
    return " ".join(value.split())[:limit]


def _commons_image(item: dict, topic: str) -> dict | None:
    """Fetch a relevant Commons image only when its reuse license is clear."""
    try:
        import requests
        from PIL import Image, ImageOps

        title = str(item.get("title", "")).strip()
        visual = str(item.get("visual_idea", "")).strip()
        query = " ".join(part for part in (topic, title, visual[:90]) if part)
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {query}",
                "gsrnamespace": 6, "gsrlimit": 6, "prop": "imageinfo",
                "iiprop": "url|extmetadata", "iiurlwidth": 1200, "format": "json",
            },
            headers={"User-Agent": "JarvisPresentation/1.0 (PowerPoint image sourcing)"},
            timeout=12,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            license_name = _plain((meta.get("LicenseShortName") or {}).get("value", ""), 80)
            lower_license = license_name.lower()
            if not any(token in lower_license for token in ("public domain", "cc0", "cc by")):
                continue
            if "nc" in lower_license or "nd" in lower_license:
                continue
            image_url = info.get("thumburl") or info.get("url") or ""
            if not image_url.startswith("https://upload.wikimedia.org/"):
                continue
            image_response = requests.get(image_url, timeout=18, headers={"User-Agent": "JarvisPresentation/1.0"})
            image_response.raise_for_status()
            if len(image_response.content) > 10_000_000:
                continue
            source_image = Image.open(io.BytesIO(image_response.content))
            if source_image.width * source_image.height > 30_000_000:
                continue
            source_image = ImageOps.fit(source_image.convert("RGB"), (1200, 675))
            stream = io.BytesIO()
            source_image.save(stream, format="JPEG", quality=88, optimize=True)
            stream.seek(0)
            author = _plain((meta.get("Artist") or {}).get("value", "Unknown"), 70)
            image_title = _plain(page.get("title", "Commons image").removeprefix("File:"), 90)
            source_page = str(info.get("descriptionurl", ""))
            credit = f"{image_title} · {author} · {license_name} · Wikimedia Commons"
            return {"stream": stream, "credit": credit, "source": source_page}
    except Exception as exc:
        print(f"[Presentation] Commons image unavailable: {exc}")
    return None


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
    if not topic:
        return "Please provide the presentation topic."
    if not isinstance(slides, list) or len(slides) < 2:
        slide_count = max(4, min(12, int(params.get("slide_count") or 8)))
        audience = str(params.get("audience") or "general professional audience").strip()
        style = str(params.get("style") or "clean, modern, professional").strip()
        requirements = str(params.get("requirements") or "").strip()
        prompt = (
            "Create a polished PowerPoint content outline as strict JSON with this shape: "
            '{"title":"...","subtitle":"...","slides":[{"title":"...","bullets":["..."],'
            '"takeaway":"...","visual_idea":"..."}],"sources":["title — URL"]}. '
            f"Topic: {topic}\nAudience: {audience}\nStyle: {style}\n"
            f"Create exactly {slide_count} content slides (cover is added separately). "
            "Use an engaging opening, logical progression, concrete examples, a useful conclusion, "
            "2-4 concise non-repetitive bullets per slide, short takeaways, and specific searchable image ideas. "
            "Keep the wording natural and presentation-ready, not essay paragraphs. Do not invent citations; "
            "include reliable source URLs only when known. Honor these user requirements: "
            f"{requirements or 'none'}"
        )
        try:
            from core import gemini
            outline = gemini.as_json(prompt, tier=gemini.TEXT, timeout_ms=75_000, default=None)
        except Exception as exc:
            return f"Could not draft the presentation: {exc}"
        if not isinstance(outline, dict) or not isinstance(outline.get("slides"), list):
            return "The presentation outline could not be generated. Check the Gemini model/API error and try again."
        title = str(outline.get("title") or topic).strip()
        params["subtitle"] = outline.get("subtitle") or params.get("subtitle", "")
        params["sources"] = outline.get("sources") or params.get("sources") or []
        slides = outline["slides"]
    if not title:
        title = topic
    if not isinstance(slides, list) or not 2 <= len(slides) <= 20:
        return "Please prepare between 2 and 20 content slides before creating the deck."

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = title[:200]
    prs.core_properties.subject = topic[:500]
    prs.core_properties.author = "JARVIS"

    _cover(prs, title, params.get("subtitle", ""), topic)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        image_futures = [pool.submit(_commons_image, item, topic) for item in slides]
        images = [future.result() for future in image_futures]
    for number, item in enumerate(slides, 1):
        if not isinstance(item, dict):
            return f"Slide {number} is invalid; each slide needs a title and bullet list."
        if not str(item.get("title") or "").strip():
            return f"Slide {number} is missing a title."
        _content_slide(prs, item, number, len(slides), images[number - 1])

    sources = list(params.get("sources") or [])
    sources.extend(
        f"Image credit: {image['credit']} — {image['source']}"
        for image in images if image
    )
    if sources:
        chunks = [sources[i:i + 12] for i in range(0, len(sources), 12)]
        for page, chunk in enumerate(chunks, 1):
            _sources_slide(prs, chunk, page, len(chunks))

    folder = _ROOT / "downloads" / "presentations"
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", topic).strip("_").lower()[:48] or "jarvis_presentation"
    target = folder / f"{slug}_{datetime.now():%Y%m%d_%H%M%S}.pptx"
    prs.save(target)
    return f"Presentation ready: {target} ({len(prs.slides)} slides)."
