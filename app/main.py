"""Lightheart: talk to an AI about ideas; they appear as notes on a scrapbook board.

    uvicorn app.main:app --reload
"""

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ops, styles
from .db import DB
from .llm.base import LLMProvider, NoKeyProvider
from .models import BookIn, ChatIn, NoteFields

log = logging.getLogger("lightheart")
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


def load_env(path=ROOT / ".env"):
    """KEY=value lines from .env (written by scripts/set-key.ps1); the environment wins."""
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()
HISTORY = 20  # the recent chat the model sees


def default_provider() -> LLMProvider:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY is not set: the AI will say so and make no cards")
        return NoKeyProvider()
    from .llm.anthropic import AnthropicProvider

    return AnthropicProvider()


def default_writer():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    from .comics import ClaudeScriptWriter

    return ClaudeScriptWriter()


def default_maker():
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    from .comics import OpenAIImageMaker

    return OpenAIImageMaker()


def create_app(provider: LLMProvider = None, db_path: str = None, writer=None, maker=None, image_dir: str = None, draw_now=False) -> FastAPI:
    """draw_now: draw a book's pictures before answering (tests); otherwise they are drawn in the background."""
    app = FastAPI(title="Lightheart")
    db = DB(db_path or os.environ.get("LIGHTHEART_DB", "lightheart.db"))
    app.state.db = db
    app.state.provider = provider or default_provider()
    app.state.writer = writer if writer is not None else default_writer()
    app.state.maker = maker if maker is not None else default_maker()
    images = Path(image_dir or os.environ.get("LIGHTHEART_IMAGES", ROOT / "images"))
    images.mkdir(parents=True, exist_ok=True)
    app.state.tasks = set()

    @app.get("/api/board")
    def board():
        return {"notes": [n.model_dump() for n in db.notes()], "messages": [m.model_dump() for m in db.messages()]}

    @app.get("/api/styles")
    def get_styles():
        return styles.public()

    @app.post("/api/chat")
    async def chat(body: ChatIn):
        text = body.content.strip()
        if not text:
            raise HTTPException(400, "empty message")
        user = db.add_message("user", text)
        recent = [{"role": m.role, "content": m.content} for m in db.messages(HISTORY)]
        try:
            result = await app.state.provider.respond(recent, ops.board_state(db.notes()))
        except Exception as e:  # a provider that raises must not break the page
            log.exception("the provider failed")
            from .llm.base import AIResult

            result = AIResult(reply="", error=str(e))
        if result.error:
            log.warning("model: %s", result.error)
        changed = ops.apply(db, result.ops, source_message_id=user.id) if not result.error or result.ops else []
        reply = (result.reply or "").strip() or ("Sorry, I lost my train of thought there. Try again?" if result.error else "")
        assistant = db.add_message("assistant", reply) if reply else None
        return {
            "reply": reply,
            "message": assistant.model_dump() if assistant else None,
            "user_message": user.model_dump(),
            "notes_changed": [n.model_dump() for n in changed],
        }

    @app.post("/api/notes")
    def create_note(fields: NoteFields):
        n = ops.new_note(fields.model_dump(exclude_none=True), db.notes())
        return db.save_note(n).model_dump()

    @app.patch("/api/notes/{note_id}")
    def patch_note(note_id: str, fields: NoteFields):
        note = db.note(note_id)
        if note is None:
            raise HTTPException(404, "no such note")
        return db.save_note(ops.updated(note, fields.model_dump(exclude_unset=True))).model_dump()

    @app.delete("/api/notes/{note_id}")
    def delete_note(note_id: str):
        if not db.delete_note(note_id):
            raise HTTPException(404, "no such note")
        return {"deleted": note_id}

    @app.get("/api/export")
    def export():
        return JSONResponse({"app": "lightheart", "version": 0, "notes": [n.model_dump() for n in db.notes()], "messages": [m.model_dump() for m in db.messages()]})

    # ---- comic books ----------------------------------------------------------------------------

    async def drawing(book_id, only=None):
        from .comics import draw_book

        if draw_now:
            await draw_book(db, app.state.maker, images, book_id, only)
        else:
            t = asyncio.create_task(draw_book(db, app.state.maker, images, book_id, only))
            app.state.tasks.add(t)
            t.add_done_callback(app.state.tasks.discard)

    @app.get("/api/books/estimate")
    def book_estimate(pages: int = 4):
        from .comics import MAX_PAGES, estimate

        return estimate(max(1, min(MAX_PAGES, pages)))

    @app.post("/api/books")
    async def make_book(body: BookIn):
        from .comics import MAX_PAGES

        if app.state.writer is None:
            raise HTTPException(400, "Set ANTHROPIC_API_KEY in .env to write the story.")
        if app.state.maker is None:
            raise HTTPException(400, "Set OPENAI_API_KEY in .env to draw the pictures.")
        notes = db.notes()
        if body.note_ids:
            notes = [n for n in notes if n.id in set(body.note_ids)]
        if not notes and not body.direction.strip():
            raise HTTPException(400, "The board is empty: add an idea first, or say what the story is about.")
        ideas = "\n".join(f"- {n.title}: {n.body}" for n in notes) or "(no cards)"
        pages = max(1, min(MAX_PAGES, body.pages))
        try:
            script = await app.state.writer.write(ideas, body.direction.strip(), pages)
        except Exception as e:
            log.exception("writing the script failed")
            raise HTTPException(502, f"The story couldn't be written ({type(e).__name__}). Try again?")
        if script is None:
            raise HTTPException(502, "The story came back empty. Try again?")
        book_id = db.add_book(script, body.direction.strip())
        await drawing(book_id)
        return db.book(book_id)

    @app.get("/api/books")
    def list_books():
        return db.books()

    @app.get("/api/books/{book_id}")
    def get_book(book_id: str):
        b = db.book(book_id)
        if not b:
            raise HTTPException(404, "no such book")
        return b

    @app.delete("/api/books/{book_id}")
    def delete_book(book_id: str):
        b = db.book(book_id)
        if not b:
            raise HTTPException(404, "no such book")
        for p in b["panels"]:
            if p["image"]:
                (images / p["image"]).unlink(missing_ok=True)
        db.delete_book(book_id)
        return {"deleted": book_id}

    @app.post("/api/panels/{panel_id}/redraw")
    async def redraw(panel_id: str):
        p = db.panel(panel_id)
        if not p:
            raise HTTPException(404, "no such panel")
        if app.state.maker is None:
            raise HTTPException(400, "Set OPENAI_API_KEY in .env to draw the pictures.")
        db.set_panel(panel_id, status="waiting")
        await drawing(p["book_id"], only=panel_id)
        return db.panel(panel_id)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.mount("/images", StaticFiles(directory=images), name="images")
    return app


logging.basicConfig(level=logging.INFO)
app = create_app() if os.environ.get("LIGHTHEART_NO_APP") != "1" else None
