"""The LLM behind a small interface, so another provider (Gemini, Z.ai) can be added later."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AIResult:
    reply: str = ""
    ops: list = field(default_factory=list)  # raw ops as the model gave them; the server validates them
    error: Optional[str] = None


class LLMProvider:
    async def respond(self, messages, board_state) -> AIResult:
        """messages: [{"role", "content"}] (recent chat); board_state: compact notes [{id, title, tags, body}]."""
        raise NotImplementedError


class FakeProvider(LLMProvider):
    """For tests and offline use: answers from a script (a list of AIResults, or a function)."""

    def __init__(self, script):
        self.script = script
        self.calls = []

    async def respond(self, messages, board_state):
        self.calls.append((messages, board_state))
        if callable(self.script):
            return self.script(messages, board_state)
        return self.script.pop(0) if self.script else AIResult(reply="")


class NoKeyProvider(LLMProvider):
    """Used when no API key is set: says so, makes no cards."""

    async def respond(self, messages, board_state):
        return AIResult(reply="I can't think yet: set ANTHROPIC_API_KEY on the server and restart it.", error="no api key")
