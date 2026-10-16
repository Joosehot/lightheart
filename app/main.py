"""Lightheart: talk to an AI about ideas; they appear as notes on a scrapbook board.

    uvicorn app.main:app --reload
"""

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import ops, styles
from .db import DB
from .llm.base import LLMProvider, NoKeyProvider
from .models import BookIn, ChatIn, NoteFields, SpeakIn, TitleIn, VoiceOpsIn, VoiceSessionIn, VoiceTurnIn

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


def default_voice():
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    from .voice import OpenAIVoice

    return OpenAIVoice()


def default_live():
    """The live voice: Gemini when its key is set (cheapest), else OpenAI; LIGHTHEART_VOICE_ENGINE picks."""
    engine = os.environ.get("LIGHTHEART_VOICE_ENGINE", "").strip().lower()
    if not engine:
        engine = "gemini" if os.environ.get("GEMINI_API_KEY") else "openai" if os.environ.get("OPENAI_API_KEY") else ""
    if engine == "gemini" and os.environ.get("GEMINI_API_KEY"):
        from .voice import GeminiLive

        return GeminiLive()
    if engine == "openai" and os.environ.get("OPENAI_API_KEY"):
        from .voice import OpenAIVoice

        return OpenAIVoice()
    return None


def create_app(provider: LLMProvider = None, db_path: str = None, writer=None, maker=None, image_dir: str = None, draw_now=False, voice=None, live=None) -> FastAPI:
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
    app.state.voice = voice if voice is not None else default_voice()
    # the live voice mode; a voice given (tests) is the live one too
    app.state.live = live if live is not None else (voice if voice is not None else default_live())

    # ---- ideas (boards) and their chats ---------------------------------------------------------

    def resolve(board_id=None, chat_id=None):
        """The idea and the chat asked for; by default the idea worked on last and its latest chat."""
        board = db.board(board_id) if board_id else db.default_board()
        if board is None:
            raise HTTPException(404, "no such idea")
        chat = db.chat(chat_id) if chat_id else None
        if chat is None or chat["board_id"] != board["id"]:
            chats = db.chats(board["id"])
            chat = chats[0] if chats else db.add_chat(board["id"])
        return board, chat

    @app.get("/api/board")
    def board(board_id: str = None, chat_id: str = None):
        b, c = resolve(board_id, chat_id)
        return {"board": b, "chat": c, "notes": [n.model_dump() for n in db.notes(b["id"])], "messages": [m.model_dump() for m in db.messages(c["id"])]}

    @app.get("/api/boards")
    def boards():
        db.default_board()  # there is always at least one idea
        return db.boards()

    @app.post("/api/boards")
    def new_board(body: TitleIn):
        b = db.add_board(body.title or "New idea")
        return {"board": b, "chat": db.chats(b["id"])[0]}

    @app.patch("/api/boards/{board_id}")
    def rename_board(board_id: str, body: TitleIn):
        if not db.board(board_id):
            raise HTTPException(404, "no such idea")
        db.rename_board(board_id, body.title)
        return db.board(board_id)

    @app.delete("/api/boards/{board_id}")
    def delete_board(board_id: str):
        if not db.board(board_id):
            raise HTTPException(404, "no such idea")
        for bk in db.books(board_id):
            for p in (db.book(bk["id"]) or {}).get("panels", []):
                if p["image"]:
                    (images / p["image"]).unlink(missing_ok=True)
        db.delete_board(board_id)
        return {"deleted": board_id}

    @app.post("/api/boards/{board_id}/chats")
    def new_chat(board_id: str):
        if not db.board(board_id):
            raise HTTPException(404, "no such idea")
        return db.add_chat(board_id)

    @app.patch("/api/chats/{chat_id}")
    def rename_chat(chat_id: str, body: TitleIn):
        if not db.chat(chat_id):
            raise HTTPException(404, "no such chat")
        db.rename_chat(chat_id, body.title)
        return db.chat(chat_id)

    @app.delete("/api/chats/{chat_id}")
    def delete_chat(chat_id: str):
        if not db.delete_chat(chat_id):
            raise HTTPException(404, "no such chat")
        return {"deleted": chat_id}

    @app.get("/api/styles")
    def get_styles():
        return styles.public()

    @app.post("/api/chat")
    async def chat(body: ChatIn):
        text = body.content.strip()
        if not text:
            raise HTTPException(400, "empty message")
        b, c = resolve(body.board_id, body.chat_id)
        first = not db.messages(c["id"])
        user = db.add_message("user", text, chat_id=c["id"])
        if first and c["title"] in ("New chat", "First chat"):  # a chat is named by its first message
            db.rename_chat(c["id"], " ".join(text.split()[:6])[:60])
        db.touch_chat(c["id"])
        db.touch_board(b["id"])
        recent = [{"role": m.role, "content": m.content} for m in db.messages(c["id"], HISTORY)]
        try:
            result = await app.state.provider.respond(recent, ops.board_state(db.notes(b["id"])))
        except Exception as e:  # a provider that raises must not break the page
            log.exception("the provider failed")
            from .llm.base import AIResult

            result = AIResult(reply="", error=str(e))
        if result.error:
            log.warning("model: %s", result.error)
        changed = ops.apply(db, result.ops, source_message_id=user.id, board_id=b["id"]) if not result.error or result.ops else []
        reply = (result.reply or "").strip() or ("Sorry, I lost my train of thought there. Try again?" if result.error else "")
        assistant = db.add_message("assistant", reply, chat_id=c["id"]) if reply else None
        return {
            "reply": reply,
            "message": assistant.model_dump() if assistant else None,
            "user_message": user.model_dump(),
            "notes_changed": [n.model_dump() for n in changed],
            "board_id": b["id"],
            "chat": db.chat(c["id"]),
        }

    @app.post("/api/notes")
    def create_note(fields: NoteFields):
        b, _ = resolve(fields.board_id)
        n = ops.new_note(fields.model_dump(exclude_none=True), db.notes(b["id"]), board_id=b["id"])
        db.touch_board(b["id"])
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
        out = []
        for b in db.boards():
            out.append({**b, "notes": [n.model_dump() for n in db.notes(b["id"])],
                        "chats": [{**c, "messages": [m.model_dump() for m in db.messages(c["id"])]} for c in db.chats(b["id"])]})
        return JSONResponse({"app": "lightheart", "version": 1, "ideas": out,
                             "notes": [n.model_dump() for n in db.notes()], "messages": [m.model_dump() for m in db.messages()]})

    # ---- comic books ----------------------------------------------------------------------------

    async def drawing(book_id, only=None):
        from .comics import draw_book

        if draw_now:
            await draw_book(db, app.state.maker, images, book_id, only)
        else:
            t = asyncio.create_task(draw_book(db, app.state.maker, images, book_id, only))
            app.state.tasks.add(t)
            t.add_done_callback(app.state.tasks.discard)

    @app.get("/api/books/art-styles")
    def art_styles():
        from .comics import ART_STYLES, DEFAULT_ART

        return {"default": DEFAULT_ART, "styles": ART_STYLES}

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
        board_obj, _ = resolve(body.board_id)
        notes = db.notes(board_obj["id"])
        if body.note_ids is not None:  # the cards the user picked (none picked: none)
            notes = [n for n in notes if n.id in set(body.note_ids)]
        if not notes and not body.direction.strip():
            raise HTTPException(400, "The board is empty: add an idea first, or say what the story is about.")
        from .comics import art_style_text

        ideas = "\n".join(f"- {n.title}: {n.body}" for n in notes) or "(no cards)"
        pages = max(1, min(MAX_PAGES, body.pages))
        art = body.art_style.strip()[:400]
        try:
            script = await app.state.writer.write(ideas, body.direction.strip(), pages, art_style_text(art))
        except Exception as e:
            log.exception("writing the script failed")
            raise HTTPException(502, f"The story couldn't be written ({type(e).__name__}). Try again?")
        if script is None:
            raise HTTPException(502, "The story came back empty. Try again?")
        book_id = db.add_book(script, body.direction.strip(), art, board_id=board_obj["id"])
        await drawing(book_id)
        return db.book(book_id)

    @app.get("/api/books")
    def list_books(board_id: str = None):
        return db.books(board_id)

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

    # ---- voice ------------------------------------------------------------------------------------

    @app.get("/api/voice")
    def voice_engine():
        return {"engine": app.state.live.engine if app.state.live else "browser"}

    # realtime voice: the browser talks to OpenAI directly; here the key is minted, and what was said
    # and the cards it makes are kept in the chat and on the board like typed ones

    @app.post("/api/voice/session")
    async def voice_session(body: VoiceSessionIn):
        if not app.state.live:
            raise HTTPException(400, "Voice mode needs GEMINI_API_KEY or OPENAI_API_KEY in .env.")
        from .llm.anthropic import TOOL
        from .llm.prompts import board_context, voice_prompt

        b, c = resolve(body.board_id, body.chat_id)
        history = "\n".join(f"{m.role}: {m.content}" for m in db.messages(c["id"], HISTORY))
        instructions = voice_prompt() + "\n" + board_context(ops.board_state(db.notes(b["id"])))
        if history:
            instructions += "\n\nThe conversation so far (typed or spoken):\n" + history
        props = TOOL["input_schema"]["properties"]
        tool = {"name": "update_board",
                "description": "Change the user's idea board: create cards, update one, or nothing.",
                "parameters": {"type": "object", "properties": {"ops": props["ops"]}, "required": ["ops"]}}
        try:
            return await app.state.live.realtime_key(instructions, tool)
        except Exception as e:
            log.exception("realtime session failed")
            raise HTTPException(502, f"Couldn't start voice mode ({e}).")

    @app.post("/api/voice/turn")
    def voice_turn(body: VoiceTurnIn):
        text = body.content.strip()
        if not text or body.role not in ("user", "assistant"):
            raise HTTPException(400, "empty")
        b, c = resolve(body.board_id, body.chat_id)
        first = not db.messages(c["id"])
        m = db.add_message(body.role, text, chat_id=c["id"])
        if first and body.role == "user" and c["title"] in ("New chat", "First chat"):
            db.rename_chat(c["id"], " ".join(text.split()[:6])[:60])
        db.touch_chat(c["id"])
        db.touch_board(b["id"])
        return {"message": m.model_dump(), "chat": db.chat(c["id"])}

    @app.post("/api/voice/ops")
    def voice_ops(body: VoiceOpsIn):
        b, c = resolve(body.board_id, body.chat_id)
        said = [m for m in db.messages(c["id"]) if m.role == "user"]
        changed = ops.apply(db, body.ops, source_message_id=said[-1].id if said else None, board_id=b["id"])
        db.touch_board(b["id"])
        return {"notes_changed": [n.model_dump() for n in changed],
                "board": ops.board_state(db.notes(b["id"]))}

    @app.post("/api/voice/transcribe")
    async def transcribe(audio: UploadFile = File(...), lang: str = Form("")):
        if not app.state.voice:
            raise HTTPException(400, "No OPENAI_API_KEY: the browser's own speech is used.")
        data = await audio.read()
        if not data:
            return {"text": ""}
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That recording is too long.")
        try:
            return {"text": await app.state.voice.transcribe(data, audio.filename or "speech.webm", lang[:2])}
        except Exception as e:
            log.exception("transcribing failed")
            raise HTTPException(502, f"Couldn't hear that ({type(e).__name__}).")

    @app.post("/api/voice/speak")
    async def speak(body: SpeakIn):
        if not app.state.voice:
            raise HTTPException(400, "No OPENAI_API_KEY: the browser's own speech is used.")
        try:
            data = await app.state.voice.speak(body.text.strip()[:4000], body.lang[:2])
        except Exception as e:
            log.exception("speaking failed")
            raise HTTPException(502, f"Couldn't speak ({type(e).__name__}).")
        return Response(content=data, media_type="audio/mpeg")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    # the page and its scripts are always fetched fresh, so a change shows on the next refresh
    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    app.mount("/images", StaticFiles(directory=images), name="images")
    return app


logging.basicConfig(level=logging.INFO)
app = create_app() if os.environ.get("LIGHTHEART_NO_APP") != "1" else None
