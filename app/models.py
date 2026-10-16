"""The board's things: notes and messages, as the API and the database see them."""

from typing import Optional

from pydantic import BaseModel, Field


class NoteFields(BaseModel):
    """What a note can be given (all optional: an update gives some, a create gets defaults)."""

    title: Optional[str] = None
    body: Optional[str] = None
    highlights: Optional[list[str]] = None
    palette: Optional[str] = None
    font: Optional[str] = None
    sticker: Optional[str] = None
    tape: Optional[bool] = None
    tags: Optional[list[str]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    rotation: Optional[float] = None
    board_id: Optional[str] = None


class Note(BaseModel):
    id: str
    title: str = ""
    body: str = ""
    highlights: list[str] = Field(default_factory=list)
    palette: str
    font: str
    sticker: Optional[str] = None
    tape: bool = True
    tags: list[str] = Field(default_factory=list)
    x: float = 0
    y: float = 0
    rotation: float = 0
    created_at: str
    updated_at: str
    source_message_id: Optional[str] = None
    board_id: Optional[str] = None


class Message(BaseModel):
    id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: str
    chat_id: Optional[str] = None


class VoiceSessionIn(BaseModel):
    board_id: Optional[str] = None
    chat_id: Optional[str] = None


class VoiceTurnIn(BaseModel):
    role: str
    content: str
    board_id: Optional[str] = None
    chat_id: Optional[str] = None


class VoiceOpsIn(BaseModel):
    ops: list = []
    board_id: Optional[str] = None
    chat_id: Optional[str] = None


class ChatIn(BaseModel):
    content: str
    board_id: Optional[str] = None
    chat_id: Optional[str] = None


class TitleIn(BaseModel):
    title: str = ""


class SpeakIn(BaseModel):
    text: str
    lang: str = "fi"


class BookIn(BaseModel):
    """A comic book from the board (or from some of its cards), with an optional wish."""

    note_ids: Optional[list[str]] = None
    direction: str = ""
    pages: int = 4
    board_id: Optional[str] = None
    art_style: str = ""  # a preset key (comics.ART_STYLES) or the user's own words
