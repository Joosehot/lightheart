"""Voice.

Voice mode is OpenAI's realtime voice (the one ChatGPT talks with): the browser talks straight to
`gpt-realtime` over WebRTC with a short-lived key minted here, the model hears and speaks itself and
puts cards on the board with the same update_board operations the chat uses. Costs roughly
10-30 cents a minute (LIGHTHEART_REALTIME_MODEL=gpt-realtime-2.1-mini is about a third of that).

transcribe/speak (text in, speech out) are kept for the API; without an OpenAI key the page falls back
to the browser's own (free) speech.
"""

import os

TRANSCRIBE_MODEL = os.environ.get("LIGHTHEART_STT_MODEL", "gpt-4o-mini-transcribe")
SPEECH_MODEL = os.environ.get("LIGHTHEART_TTS_MODEL", "gpt-4o-mini-tts")
REALTIME_MODEL = os.environ.get("LIGHTHEART_REALTIME_MODEL", "gpt-realtime-2.1")
VOICE = os.environ.get("LIGHTHEART_VOICE", "marin")  # OpenAI's newest, most natural voice (also: cedar)
STYLE = "Warm, calm and curious, like a thoughtful friend who loves ideas. Natural pace, not too slow."
ACCENT = {
    "fi": "Speak Finnish like a native speaker from Finland: Finnish vowels and rhythm, stress on the first syllable, no English accent.",
    "en": "Speak natural, relaxed English.",
}


class Voice:
    async def transcribe(self, audio: bytes, filename: str, lang: str) -> str:
        raise NotImplementedError

    async def speak(self, text: str, lang: str) -> bytes:
        raise NotImplementedError

    async def realtime_key(self, instructions: str, tools: list) -> dict:
        """A short-lived key for one realtime voice session, its model, voice and tools set here."""
        raise NotImplementedError


class OpenAIVoice(Voice):
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

    async def realtime_key(self, instructions, tools):
        import httpx

        session = {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "instructions": instructions,
            "tools": tools,
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
        return {"key": r.json()["value"], "model": REALTIME_MODEL}


class FakeVoice(Voice):
    def __init__(self, heard="hello"):
        self.heard = heard
        self.spoken = []

    async def transcribe(self, audio, filename, lang):
        return self.heard if audio else ""

    async def speak(self, text, lang):
        self.spoken.append(text)
        return b"ID3fake-mp3"

    async def realtime_key(self, instructions, tools):
        self.session = {"instructions": instructions, "tools": tools}
        return {"key": "ek_fake", "model": "fake-realtime"}
