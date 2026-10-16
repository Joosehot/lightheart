"""The comic book: Claude writes the script from the board, an image model draws each panel.

Speech bubbles and captions are the page's own text over the picture (image models write text badly,
Finnish worst of all); the pictures have no words in them.
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
STYLE = ("A warm hand-drawn comic book panel: clean confident ink outlines, soft watercolor colors on cream paper, "
         "cozy and expressive, consistent characters. No text, no letters, no speech bubbles, no captions in the picture.")


# ---- the script --------------------------------------------------------------------------------

SCRIPT_TOOL = {
    "name": "write_comic",
    "description": "Write a short comic book script from the user's ideas.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The book's title, in the user's language."},
            "characters": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "look": {"type": "string", "description": "In English: a precise visual description (age, build, hair, clothes, colors) so every panel draws them the same."},
                }, "required": ["name", "look"]},
            },
            "pages": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "panels": {"type": "array", "items": {"type": "object", "properties": {
                        "scene": {"type": "string", "description": "In English: what the picture shows (who, where, action, mood, framing). The characters by name."},
                        "caption": {"type": "string", "description": "Narration box text in the user's language, or empty."},
                        "bubbles": {"type": "array", "items": {"type": "object", "properties": {
                            "speaker": {"type": "string"}, "text": {"type": "string", "description": "Speech, in the user's language, short."},
                        }, "required": ["speaker", "text"]}},
                    }, "required": ["scene"]}},
                }, "required": ["panels"]},
            },
        },
        "required": ["title", "characters", "pages"],
    },
}


def script_prompt(pages):
    return f"""You turn the user's ideas from their idea board into a short comic book that reads well.
Write exactly {pages} pages, each with 2-{PANELS_PER_PAGE} panels. Give it a clear beginning, a turn and an ending.
Captions and speech: short, in the language the user's ideas are written in (Finnish in, Finnish out); at most {MAX_BUBBLES} speech bubbles per panel; some panels need no words at all.
Scenes and character looks: in English, concrete and visual, so an image model can draw them; name the characters in the scene and keep their looks the same.
Answer by calling the write_comic tool."""


@dataclass
class Script:
    title: str
    characters: list = field(default_factory=list)
    pages: list = field(default_factory=list)  # [[{scene, caption, bubbles}]]


def clean_script(data, pages):
    """Whatever the model gave, a script that fits: limits kept, empty panels dropped, never raises."""
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "Untitled").strip()[:80]
    chars = []
    for c in data.get("characters") or []:
        if isinstance(c, dict) and str(c.get("name") or "").strip():
            chars.append({"name": str(c["name"]).strip()[:40], "look": str(c.get("look") or "").strip()[:400]})
    out_pages = []
    for p in (data.get("pages") or [])[:pages]:
        panels = []
        for pn in (p.get("panels") if isinstance(p, dict) else None) or []:
            if not isinstance(pn, dict) or not str(pn.get("scene") or "").strip():
                continue
            bubbles = []
            for b in (pn.get("bubbles") or [])[:MAX_BUBBLES]:
                if isinstance(b, dict) and str(b.get("text") or "").strip():
                    bubbles.append({"speaker": str(b.get("speaker") or "").strip()[:40], "text": str(b["text"]).strip()[:160]})
            panels.append({"scene": str(pn["scene"]).strip()[:700], "caption": str(pn.get("caption") or "").strip()[:200], "bubbles": bubbles})
        if panels:
            out_pages.append(panels[:PANELS_PER_PAGE])
    if not out_pages:
        return None
    return Script(title=title, characters=chars, pages=out_pages)


class ScriptWriter:
    async def write(self, ideas: str, direction: str, pages: int):
        raise NotImplementedError


class ClaudeScriptWriter(ScriptWriter):
    def __init__(self, model=None):
        import anthropic

        self.client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        # the story is written by a stronger model than the chat's (LIGHTHEART_STORY_MODEL overrides it)
        self.model = model or os.environ.get("LIGHTHEART_STORY_MODEL") or "claude-sonnet-5-5"

    async def write(self, ideas, direction, pages):
        user = f"My ideas:\n{ideas}\n\n" + (f"What I'd like: {direction}\n" if direction else "") + f"Make it {pages} pages."
        resp = await self.client.messages.create(
            model=self.model, max_tokens=4000, system=script_prompt(pages),
            messages=[{"role": "user", "content": user}], tools=[SCRIPT_TOOL], tool_choice={"type": "auto"},
        )
        call = next((b for b in resp.content if getattr(b, "type", "") == "tool_use" and b.name == "write_comic"), None)
        return clean_script(call.input if call else None, pages)


class FakeScriptWriter(ScriptWriter):
    def __init__(self, data=None):
        self.data = data
        self.calls = []

    async def write(self, ideas, direction, pages):
        self.calls.append((ideas, direction, pages))
        data = self.data or {
            "title": "Testikirja",
            "characters": [{"name": "Aino", "look": "a girl with a yellow raincoat"}],
            "pages": [{"panels": [{"scene": f"Aino on page {p + 1}, panel {i + 1}", "caption": "Olipa kerran", "bubbles": [{"speaker": "Aino", "text": "Hei!"}]} for i in range(3)]} for p in range(pages)],
        }
        return clean_script(data, pages)


# ---- the pictures ------------------------------------------------------------------------------

def panel_prompt(script_characters, scene):
    """The style, every character the scene names (with their looks), the scene."""
    who = [c for c in script_characters if c["name"] and c["name"].lower() in scene.lower()]
    looks = " ".join(f"{c['name']}: {c['look']}." for c in who)
    return f"{STYLE} {looks} Scene: {scene}".strip()


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
        scene = prompt.split("Scene:")[-1].strip()[:90].replace("&", "&amp;").replace("<", "&lt;")
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
    script_chars = book["characters"]
    todo = [p for p in book["panels"] if (only is None and p["status"] != "done") or p["id"] == only]
    gate = asyncio.Semaphore(parallel)

    async def one(p):
        async with gate:
            db.set_panel(p["id"], status="drawing")
            try:
                data = await maker.draw(panel_prompt(script_chars, p["scene"]))
                name = f"{p['id']}.{maker.ext}"
                (image_dir / name).write_bytes(data)
                db.set_panel(p["id"], status="done", image=name)
            except Exception as e:
                log.exception("drawing panel %s failed", p["id"])
                db.set_panel(p["id"], status="failed", error=f"{type(e).__name__}")

    await asyncio.gather(*(one(p) for p in todo))
