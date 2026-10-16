"""Voice: what is said becomes text, the reply becomes speech.

Claude's own voice mode is only in Claude's apps (no API), so the voice here is OpenAI's: accurate
transcription (Finnish too) and a natural voice, a few cents a minute. Without an OpenAI key the page
falls back to the browser's own (free) speech.
"""

import os

TRANSCRIBE_MODEL = os.environ.get("LIGHTHEART_STT_MODEL", "gpt-4o-mini-transcribe")
SPEECH_MODEL = os.environ.get("LIGHTHEART_TTS_MODEL", "gpt-4o-mini-tts")
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


class FakeVoice(Voice):
    def __init__(self, heard="hello"):
        self.heard = heard
        self.spoken = []

    async def transcribe(self, audio, filename, lang):
        return self.heard if audio else ""

    async def speak(self, text, lang):
        self.spoken.append(text)
        return b"ID3fake-mp3"
