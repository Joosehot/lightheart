"""The comic book: Claude writes the script from the cards the user picks, an image model draws each panel.

Speech bubbles and captions are the page's own text over the picture (image models write text badly,
Finnish worst of all); the pictures have no words in them.

The picture instructions are detailed, because the image model sees each panel alone: the art style
(a preset or the user's own words), the book's world (era, place, palette, light, the same in every
panel), the shot, the setting, what happens, and every character in the panel with their exact look.
"""

import asyncio
import base64
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("lightheart.comics")

MAX_PAGES = 6
PANELS_PER_PAGE = 4
MAX_BUBBLES = 2
# the cheapest drawing in October 2026: OpenAI gpt-image-2, low quality, 1024x1024, about $0.006
PRICE_PER_IMAGE = {"low": 0.006, "medium": 0.03, "high": 0.13}

# art styles the user can pick (or write their own)
ART_STYLES = {
    "watercolor": "warm hand-drawn comic art: clean confident ink outlines, soft watercolor washes on cream paper, gentle light, cozy and expressive",
    "manga": "black and white manga: crisp ink lines, screentone shading, dynamic angles, expressive eyes, speed lines where there is motion",
    "ligne-claire": "ligne claire comic art like classic European albums: even clean outlines, flat bright colors, no hatching, detailed backgrounds",
    "noir": "noir comic art: heavy black shadows, high contrast, a limited palette of black, grey and one accent color, rain and hard light",
    "picture-book": "a children's picture book: soft colored pencil and gouache, rounded friendly shapes, warm pastel colors, simple backgrounds",
}
DEFAULT_ART = "watercolor"
SHOTS = ["establishing wide shot", "wide shot", "medium shot", "close-up", "extreme close-up", "over-the-shoulder shot", "low angle", "high angle", "bird's-eye view"]


# ---- the script --------------------------------------------------------------------------------

SCRIPT_TOOL = {
    "name": "write_comic",
    "description": "Write a short comic book script from the user's ideas, with picture instructions an image model can follow.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The book's title, in the user's language."},
            "world": {"type": "string", "description": "In English: the look of the whole book, kept the same in every panel: era, place, season, color palette, light."},
            "characters": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "look": {"type": "string", "description": "In English, precise and fixed: age, build, face, hair (color, length, style), clothes with their colors, one distinctive detail. The same words every panel."},
                }, "required": ["name", "look"]},
            },
            "pages": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "panels": {"type": "array", "items": {"type": "object", "properties": {
                        "shot": {"type": "string", "enum": SHOTS},
                        "setting": {"type": "string", "description": "In English: where exactly, time of day, weather, light, the important objects."},
                        "action": {"type": "string", "description": "In English: who is in the panel (by name), what they do, their poses, expressions and where they look."},
                        "scene": {"type": "string", "description": "In English: one sentence, what this panel shows."},
                        "caption": {"type": "string", "description": "Narration box text in the user's language, or empty."},
                        "bubbles": {"type": "array", "items": {"type": "object", "properties": {
                            "speaker": {"type": "string"}, "text": {"type": "string", "description": "Speech, in the user's language, short."},
                        }, "required": ["speaker", "text"]}},
                    }, "required": ["shot", "setting", "action", "scene"]}},
                }, "required": ["panels"]},
            },
        },
        "required": ["title", "world", "characters", "pages"],
    },
}


def script_prompt(pages, art_style):
    return f"""You turn the user's ideas into a short comic book that reads well, and you direct its pictures.
Write exactly {pages} pages, each with 2-{PANELS_PER_PAGE} panels. Give it a clear beginning, a turn and an ending.

Words: captions and speech are short, in the language the user's ideas are written in (Finnish in, Finnish out); at most {MAX_BUBBLES} speech bubbles per panel; some panels need no words at all.

Pictures: an image model draws every panel alone, seeing nothing else, so tell it everything, in English:
- world: the book's fixed look (era, place, palette, light), the same in every panel;
- characters: each one's exact look, fixed once, so they are drawn the same every time;
- every panel: the shot (vary them like a film: open a scene wide, come close for feelings), the setting, and the action (who, what they do, poses, expressions).
The pictures will be drawn in this art style: {art_style}.

Answer by calling the write_comic tool."""


@dataclass
class Script:
    title: str
    world: str = ""
    characters: list = field(default_factory=list)
    pages: list = field(default_factory=list)  # [[{shot, setting, action, scene, caption, bubbles}]]


def _s(x, n):
    return str(x or "").strip()[:n]


def clean_script(data, pages):
    """Whatever the model gave, a script that fits: limits kept, empty panels dropped, never raises."""
    if not isinstance(data, dict):
        return None
    chars = []
    for c in data.get("characters") or []:
        if isinstance(c, dict) and _s(c.get("name"), 40):
            chars.append({"name": _s(c["name"], 40), "look": _s(c.get("look"), 500)})
    out_pages = []
    for p in (data.get("pages") or [])[:pages]:
        panels = []
        for pn in (p.get("panels") if isinstance(p, dict) else None) or []:
            if not isinstance(pn, dict):
                continue
            scene = _s(pn.get("scene"), 400) or _s(pn.get("action"), 400)
            if not scene:
                continue
            bubbles = []
            for b in (pn.get("bubbles") or [])[:MAX_BUBBLES]:
                if isinstance(b, dict) and _s(b.get("text"), 160):
                    bubbles.append({"speaker": _s(b.get("speaker"), 40), "text": _s(b["text"], 160)})
            shot = pn.get("shot") if pn.get("shot") in SHOTS else "medium shot"
            panels.append({"shot": shot, "setting": _s(pn.get("setting"), 500), "action": _s(pn.get("action"), 600), "scene": scene,
                           "caption": _s(pn.get("caption"), 200), "bubbles": bubbles})
        if panels:
            out_pages.append(panels[:PANELS_PER_PAGE])
    if not out_pages:
        return None
    return Script(title=_s(data.get("title"), 80) or "Untitled", world=_s(data.get("world"), 600), characters=chars, pages=out_pages)


def art_style_text(art):
    """A preset's description, or the user's own words."""
    art = (art or "").strip()
    return ART_STYLES.get(art) or art[:400] or ART_STYLES[DEFAULT_ART]


class ScriptWriter:
    async def write(self, ideas: str, direction: str, pages: int, art_style: str):
        raise NotImplementedError


class ClaudeScriptWriter(ScriptWriter):
    def __init__(self, model=None):
        import anthropic

        self.client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        # the story is written by a stronger model than the chat's (LIGHTHEART_STORY_MODEL overrides it)
        self.model = model or os.environ.get("LIGHTHEART_STORY_MODEL") or "claude-sonnet-5-5"

    async def write(self, ideas, direction, pages, art_style):
        user = f"My ideas:\n{ideas}\n\n" + (f"What I'd like: {direction}\n" if direction else "") + f"Make it {pages} pages."
        resp = await self.client.messages.create(
            model=self.model, max_tokens=6000, system=script_prompt(pages, art_style),
            messages=[{"role": "user", "content": user}], tools=[SCRIPT_TOOL], tool_choice={"type": "auto"},
        )
        call = next((b for b in resp.content if getattr(b, "type", "") == "tool_use" and b.name == "write_comic"), None)
        return clean_script(call.input if call else None, pages)


class FakeScriptWriter(ScriptWriter):
    def __init__(self, data=None):
        self.data = data
        self.calls = []

    async def write(self, ideas, direction, pages, art_style):
        self.calls.append((ideas, direction, pages, art_style))
        data = self.data or {
            "title": "Testikirja",
            "world": "a small harbour town in autumn, grey-blue sea, warm lamplight",
            "characters": [{"name": "Aino", "look": "a girl of ten with a yellow raincoat and red boots"}],
            "pages": [{"panels": [{"shot": "wide shot", "setting": "the harbour at dusk", "action": f"Aino waves from the pier (page {p + 1}, panel {i + 1})",
                                   "scene": f"Aino on page {p + 1}, panel {i + 1}", "caption": "Olipa kerran", "bubbles": [{"speaker": "Aino", "text": "Hei!"}]} for i in range(3)]} for p in range(pages)],
        }
        return clean_script(data, pages)


# ---- the pictures ------------------------------------------------------------------------------

def panel_prompt(book, panel):
    """Everything the image model needs for one panel, in order of importance."""
    text = " ".join((panel.get("action") or "", panel.get("scene") or "")).lower()
    who = [c for c in book["characters"] if c["name"] and c["name"].lower() in text]
    lines = [
        "A single comic book panel.",
        f"Art style: {art_style_text(book.get('art_style'))}.",
    ]
    if book.get("world"):
        lines.append(f"World (keep it the same as in every other panel): {book['world']}.")
    lines.append(f"Shot: {panel.get('shot') or 'medium shot'}.")
    if panel.get("setting"):
        lines.append(f"Setting: {panel['setting']}.")
    for c in who:
        lines.append(f"Character {c['name']} (draw exactly like this, same face, hair, clothes and colors): {c['look']}.")
    lines.append(f"Action: {panel.get('action') or panel.get('scene')}.")
    lines.append(f"Scene: {panel.get('scene')}.")
    lines.append("Composition: keep the top-left corner and a strip along the bottom calm and uncluttered; speech bubbles and captions are added there afterwards.")
    lines.append("No text, no letters, no speech bubbles, no captions, no signature, no panel borders in the picture.")
    return "\n".join(lines)


class ImageMaker:
    ext = "png"

    async def draw(self, prompt: str) -> bytes:
        raise NotImplementedError


class OpenAIImageMaker(ImageMaker):
    def __init__(self, quality=None):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model = os.environ.get("LIGHTHEART_IMAGE_MODEL", "gpt-image-2")
        self.quality = quality or os.environ.get("LIGHTHEART_IMAGE_QUALITY", "low")

    async def draw(self, prompt):
        r = await self.client.images.generate(model=self.model, prompt=prompt, size="1024x1024", quality=self.quality, n=1)
        return base64.b64decode(r.data[0].b64_json)


class FakeImageMaker(ImageMaker):
    """Draws a plain placeholder (an SVG with the scene), for tests and for running without a key."""

    ext = "svg"

    def __init__(self):
        self.prompts = []

    async def draw(self, prompt):
        self.prompts.append(prompt)
        scene = prompt.split("Scene:")[-1].split("\n")[0].strip()[:90].replace("&", "&amp;").replace("<", "&lt;")
        return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1024 1024'><rect width='1024' height='1024' fill='#f3e9d6'/>"
                f"<text x='512' y='512' font-size='34' text-anchor='middle' fill='#8a7a60' font-family='sans-serif'>{scene}</text></svg>").encode()


def estimate(pages, quality=None):
    q = quality or os.environ.get("LIGHTHEART_IMAGE_QUALITY", "low")
    images = pages * 3  # about three panels a page
    return {"pages": pages, "images": images, "quality": q, "usd": round(images * PRICE_PER_IMAGE.get(q, PRICE_PER_IMAGE["low"]), 3)}


async def draw_book(db, maker: ImageMaker, image_dir: Path, book_id: str, only=None, parallel=3):
    """Draw every panel of a book still waiting (or just `only`), a few at a time; never raises."""
    image_dir.mkdir(parents=True, exist_ok=True)
    book = db.book(book_id)
    if not book:
        return
    todo = [p for p in book["panels"] if (only is None and p["status"] != "done") or p["id"] == only]
    gate = asyncio.Semaphore(parallel)

    async def one(p):
        async with gate:
            db.set_panel(p["id"], status="drawing")
            try:
                data = await maker.draw(panel_prompt(book, p))
                name = f"{p['id']}.{maker.ext}"
                (image_dir / name).write_bytes(data)
                db.set_panel(p["id"], status="done", image=name)
            except Exception as e:
                log.exception("drawing panel %s failed", p["id"])
                db.set_panel(p["id"], status="failed", error=f"{type(e).__name__}")

    await asyncio.gather(*(one(p) for p in todo))
