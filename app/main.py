"""Lightheart: talk to an AI about ideas; they appear as notes on a scrapbook board.

    uvicorn app.main:app --reload
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import ops, styles
from .db import DB
from .llm.base import LLMProvider, NoKeyProvider
from .models import ChatIn, NoteFields

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


def create_app(provider: LLMProvider = None, db_path: str = None) -> FastAPI:
    app = FastAPI(title="Lightheart")
    db = DB(db_path or os.environ.get("LIGHTHEART_DB", "lightheart.db"))
    app.state.db = db
    app.state.provider = provider or default_provider()

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

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


logging.basicConfig(level=logging.INFO)
app = create_app() if os.environ.get("LIGHTHEART_NO_APP") != "1" else None
