"""Anthropic's API, with tool use for structured output (never free-text JSON).

ASSUMPTION: one provider, one model in v0, from LIGHTHEART_MODEL (default a mid-tier Claude model).
"""

import logging
import os

from .. import styles
from .base import AIResult, LLMProvider
from .prompts import board_context, system_prompt

log = logging.getLogger("lightheart.llm")

DEFAULT_MODEL = "claude-sonnet-5-5"

NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "highlights": {"type": "array", "items": {"type": "string"}},
        "palette": {"type": "string", "enum": list(styles.PALETTES)},
        "font": {"type": "string", "enum": list(styles.FONTS)},
        "sticker": {"type": ["string", "null"], "enum": list(styles.STICKERS) + [None]},
        "tape": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}

TOOL = {
    "name": "update_board",
    "description": "Answer the user and change their idea board: create a card, update one, or nothing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reply": {"type": "string", "description": "A short, warm, conversational answer (1-4 sentences), in the user's language."},
            "ops": {
                "type": "array",
                "maxItems": styles.MAX_OPS_PER_TURN,
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": ["create", "update", "none"]},
                        "note": {**NOTE_SCHEMA, "description": "For create: the new card."},
                        "id": {"type": "string", "description": "For update: the id of an existing card."},
                        "fields": {**NOTE_SCHEMA, "description": "For update: only the fields that change."},
                    },
                    "required": ["op"],
                },
            },
        },
        "required": ["reply", "ops"],
    },
}


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key=None, model=None, max_tokens=1024):
        import anthropic

        self.client = anthropic.AsyncAnthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model or os.environ.get("LIGHTHEART_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens

    async def respond(self, messages, board_state):
        system = system_prompt() + "\n" + board_context(board_state)
        try:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
                tools=[TOOL],
                # forcing the tool ("tool"/"any") is not supported by every model: the prompt asks for it,
                # and a reply without the call is shown as text with no card
                tool_choice={"type": "auto"},
            )
        except Exception as e:  # network, auth, rate limit: the page still works
            log.exception("the model call failed")
            return AIResult(reply="", error=f"{type(e).__name__}: {e}")
        text = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        call = next((b for b in resp.content if getattr(b, "type", "") == "tool_use" and b.name == "update_board"), None)
        if call is None or not isinstance(call.input, dict):
            log.warning("no update_board call in the response")
            return AIResult(reply=text, error="no tool call")
        data = call.input
        reply = data.get("reply") if isinstance(data.get("reply"), str) else text
        ops = data.get("ops") if isinstance(data.get("ops"), list) else []
        return AIResult(reply=reply or text, ops=ops)
