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


class Message(BaseModel):
    id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: str


class ChatIn(BaseModel):
    content: str
