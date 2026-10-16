"""Voice.

Voice mode is a live voice model that hears and speaks itself and puts cards on the board with the
same update_board operations the chat uses. The browser talks to it directly with a short-lived key
minted here (realtime_key), so the API key never leaves the server.

- Gemini Live (default when GEMINI_API_KEY is set): `gemini-3.8-live` over a WebSocket, about
  1-3 cents a minute.
- OpenAI realtime (LIGHTHEART_VOICE_ENGINE=openai): `gpt-realtime-2.1` over WebRTC, the voice
  ChatGPT talks with, about 5-15 cents a minute (LIGHTHEART_REALTIME_MODEL=gpt-realtime-2.1-mini
  is about a third of that).

transcribe/speak (text in, speech out, OpenAI) are kept for the API; with no key at all the page falls
back to the browser's own (free) speech.
"""

import datetime as dt
import os

TRANSCRIBE_MODEL = os.environ.get("LIGHTHEART_STT_MODEL", "gpt-4o-mini-transcribe")
SPEECH_MODEL = os.environ.get("LIGHTHEART_TTS_MODEL", "gpt-4o-mini-tts")
REALTIME_MODEL = os.environ.get("LIGHTHEART_REALTIME_MODEL", "gpt-realtime-2.1")
VOICE = os.environ.get("LIGHTHEART_VOICE", "marin")  # OpenAI's newest, most natural voice (also: cedar)
GEMINI_MODEL = os.environ.get("LIGHTHEART_GEMINI_MODEL", "models/gemini-3.8-live")
GEMINI_VOICE = os.environ.get("LIGHTHEART_GEMINI_VOICE", "Aoede")
GEMINI_WS = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained?access_token="
STYLE = "Warm, calm and curious, like a thoughtful friend who loves ideas. Natural pace, not too slow."
ACCENT = {
    "fi": "Speak Finnish like a native speaker from Finland: Finnish vowels and rhythm, stress on the first syllable, no English accent.",
    "en": "Speak natural, relaxed English.",
}


class Voice:
    engine = "openai"

    async def transcribe(self, audio: bytes, filename: str, lang: str) -> str:
        raise NotImplementedError

    async def speak(self, text: str, lang: str) -> bytes:
        raise NotImplementedError

    async def realtime_key(self, instructions: str, tool: dict) -> dict:
        """A short-lived key for one live voice session, its model, voice and tool set here.
        tool: {"name", "description", "parameters" (JSON schema)}."""
        raise NotImplementedError


class OpenAIVoice(Voice):
    engine = "openai"

    def __init__(self):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    async def transcribe(self, audio, filename, lang):
        r = await self.client.audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=(filename, audio), language=lang or None)
        return (r.text or "").strip()

    async def speak(self, text, lang):
        r = await self.client.audio.speech.create(model=SPEECH_MODEL, voice=VOICE, input=text[:4000], instructions=f"{STYLE} {ACCENT.get(lang, '')}".strip(), response_format="mp3")
        data = getattr(r, "content", None)
        if data is None:
            data = await r.aread()
        return data

    async def realtime_key(self, instructions, tool):
        import httpx

        session = {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "instructions": instructions,
            "tools": [{"type": "function", **tool}],
            "tool_choice": "auto",
            "audio": {
                "input": {"transcription": {"model": TRANSCRIBE_MODEL}, "turn_detection": {"type": "semantic_vad"}},
                "output": {"voice": VOICE},
            },
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.openai.com/v1/realtime/client_secrets",
                headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY')}"},
                json={"session": session},
            )
        if r.status_code >= 400:
            raise RuntimeError(f"realtime key: {r.status_code} {r.text[:300]}")
        return {"engine": "openai", "key": r.json()["value"], "model": REALTIME_MODEL}


def gemini_schema(s):
    """JSON schema -> Gemini's OpenAPI subset: no type lists, no null in enums."""
    if isinstance(s, list):
        return [gemini_schema(x) for x in s]
    if not isinstance(s, dict):
        return s
    out = {}
    for k, v in s.items():
        if k == "type" and isinstance(v, list):
            types = [t for t in v if t != "null"]
            out["type"] = types[0] if types else "string"
            if "null" in v:
                out["nullable"] = True
        elif k == "enum":
            out["enum"] = [x for x in v if x is not None]
        else:
            out[k] = gemini_schema(v)
    return out


class GeminiLive(Voice):
    """Gemini Live: only the live voice (no transcribe/speak)."""

    engine = "gemini"

    async def realtime_key(self, instructions, tool):
        import httpx

        def at(minutes):
            return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

        setup = {
            "model": GEMINI_MODEL,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_VOICE}}},
            },
            "systemInstruction": {"parts": [{"text": instructions}]},
            "tools": [{"functionDeclarations": [{**tool, "parameters": gemini_schema(tool["parameters"])}]}],
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }
        # one session, started within 2 minutes, at most 30 minutes long; the setup is locked into it
        body = {"uses": 1, "expireTime": at(30), "newSessionExpireTime": at(2), "bidiGenerateContentSetup": setup}
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/auth_tokens",
                headers={"x-goog-api-key": os.environ.get("GEMINI_API_KEY", "").strip()},
                json=body,
            )
        if r.status_code >= 400:
            raise RuntimeError(f"gemini key: {r.status_code} {r.text[:300]}")
        token = r.json()["name"]
        return {"engine": "gemini", "key": token, "model": GEMINI_MODEL, "url": GEMINI_WS + token}


class FakeVoice(Voice):
    engine = "openai"

    def __init__(self, heard="hello"):
        self.heard = heard
        self.spoken = []

    async def transcribe(self, audio, filename, lang):
        return self.heard if audio else ""

    async def speak(self, text, lang):
        self.spoken.append(text)
        return b"ID3fake-mp3"

    async def realtime_key(self, instructions, tool):
        self.session = {"instructions": instructions, "tools": [tool]}
        return {"engine": "openai", "key": "ek_fake", "model": "fake-realtime"}
