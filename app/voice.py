"""Voice.

Voice mode is a live voice model that hears and speaks itself and puts cards on the board with the
same update_board operations the chat uses. The browser talks to it directly with a short-lived key
minted here (realtime_key), so the API key never leaves the server.

- Gemini Live (default when GEMINI_API_KEY is set): `gemini-3.8-live` over a WebSocket, about
  1-3 cents a minute.
- OpenAI realtime (LIGHTHEART_VOICE_ENGINE=openai): `gpt-realtime-2.1` over WebRTC, the voice
  ChatGPT talks with, about 5-15 cents a minute (LIGHTHEART_REALTIME_MODEL=gpt-realtime-2.1-mini
  is about a third of that).

The user picks the voice, how it talks (a comic-book character or their own description) and how
fast; preview() lets them hear it first.

transcribe/speak (text in, speech out, OpenAI) are kept for the API; with no key at all the page falls
back to the browser's own (free) speech.
"""

import asyncio
import base64
import datetime as dt
import json
import os
import struct

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

# ---- the voice the user picks: which voice, how it talks, how fast ---------------------------------

# Gemini's voices with Google's own one-word character for each
GEMINI_VOICES = [
    ("Aoede", "breezy"), ("Puck", "upbeat"), ("Zephyr", "bright"), ("Kore", "firm"), ("Charon", "informative"),
    ("Fenrir", "excitable"), ("Leda", "youthful"), ("Orus", "firm"), ("Callirrhoe", "easy-going"), ("Autonoe", "bright"),
    ("Enceladus", "breathy"), ("Iapetus", "clear"), ("Umbriel", "easy-going"), ("Algieba", "smooth"), ("Despina", "smooth"),
    ("Erinome", "clear"), ("Algenib", "gravelly"), ("Rasalgethi", "informative"), ("Laomedeia", "upbeat"), ("Achernar", "soft"),
    ("Alnilam", "firm"), ("Schedar", "even"), ("Gacrux", "mature"), ("Pulcherrima", "forward"), ("Achird", "friendly"),
    ("Zubenelgenubi", "casual"), ("Vindemiatrix", "gentle"), ("Sadachbia", "lively"), ("Sadaltager", "knowledgeable"), ("Sulafat", "warm"),
]
OPENAI_VOICES = [
    ("marin", "natural"), ("cedar", "natural, deeper"), ("coral", "warm"), ("sage", "calm"), ("shimmer", "bright"),
    ("ballad", "soft"), ("verse", "expressive"), ("ash", "clear"), ("alloy", "neutral"), ("echo", "even"),
]

# how it talks: comic-book characters it can play, or the user's own description ("custom")
SPEECH_STYLES = {
    "friend": ("Warm friend", "a warm, calm and curious friend who loves ideas"),
    "narrator": ("Comic narrator", "a comic book narrator reading the caption boxes aloud: vivid and theatrical, building suspense with little pauses"),
    "sidekick": ("Cartoon sidekick", "a bouncy cartoon sidekick: playful, excited and expressive, quick to laugh"),
    "hero": ("Superhero", "a bold superhero: confident, upbeat, big heroic energy"),
    "noir": ("Noir detective", "a hard-boiled noir narrator: low, dry and moody, unhurried, with a wry edge"),
    "storyteller": ("Picture-book reader", "a gentle picture-book reader at bedtime: soft, cosy, full of quiet wonder"),
}
SPEEDS = {"slow": "Speak slowly and clearly.", "normal": "Speak at a natural pace.", "fast": "Speak briskly, with energy."}
DEFAULT_SETTINGS = {"voice": "", "style": "friend", "custom": "", "speed": "normal"}
PREVIEW_LINE = "Hei! Minä olen ideakumppanisi. Kerro, mitä mielessäsi pyörii, niin tehdään siitä tarina."


def voices_for(engine):
    return GEMINI_VOICES if engine == "gemini" else OPENAI_VOICES


def clean_settings(engine, s):
    """Only known values; an unknown voice falls back to the engine's default."""
    s = {**DEFAULT_SETTINGS, **{k: v for k, v in (s or {}).items() if k in DEFAULT_SETTINGS and isinstance(v, str)}}
    names = [v for v, _ in voices_for(engine)]
    default = GEMINI_VOICE if engine == "gemini" else VOICE
    if s["voice"] not in names:
        s["voice"] = default if default in names else names[0]
    if s["style"] not in SPEECH_STYLES and s["style"] != "custom":
        s["style"] = "friend"
    if s["speed"] not in SPEEDS:
        s["speed"] = "normal"
    s["custom"] = s["custom"].strip()[:400]
    return s


def manner(s):
    """The settings as words for the model: who it sounds like and how fast."""
    if s["style"] == "custom" and s["custom"]:
        how = s["custom"]
    else:
        how = SPEECH_STYLES.get(s["style"], SPEECH_STYLES["friend"])[1]
    return f"Your voice and manner: talk like {how}. Stay this character in every reply. {SPEEDS[s['speed']]}"


def wav(pcm: bytes, rate=24000):
    """16-bit mono PCM in a WAV file."""
    head = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return head + b"data" + struct.pack("<I", len(pcm)) + pcm


class Voice:
    engine = "openai"

    async def transcribe(self, audio: bytes, filename: str, lang: str) -> str:
        raise NotImplementedError

    async def speak(self, text: str, lang: str) -> bytes:
        raise NotImplementedError

    async def preview(self, settings: dict) -> tuple:
        """A short sample of the voice as set: (audio bytes, media type)."""
        raise NotImplementedError

    async def realtime_key(self, instructions: str, tool: dict, voice: str = None) -> dict:
        """A short-lived key for one live voice session, its model, voice and tool set here.
        tool: {"name", "description", "parameters" (JSON schema)}, or None."""
        raise NotImplementedError


class OpenAIVoice(Voice):
    engine = "openai"

    def __init__(self):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    async def transcribe(self, audio, filename, lang):
        r = await self.client.audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=(filename, audio), language=lang or None)
        return (r.text or "").strip()

    async def _speech(self, text, voice, instructions):
        r = await self.client.audio.speech.create(model=SPEECH_MODEL, voice=voice, input=text[:4000], instructions=instructions, response_format="mp3")
        data = getattr(r, "content", None)
        if data is None:
            data = await r.aread()
        return data

    async def speak(self, text, lang):
        return await self._speech(text, VOICE, f"{STYLE} {ACCENT.get(lang, '')}".strip())

    async def preview(self, settings):
        return await self._speech(PREVIEW_LINE, settings["voice"], f"{manner(settings)} {ACCENT['fi']}"), "audio/mpeg"

    async def realtime_key(self, instructions, tool, voice=None):
        import httpx

        session = {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "instructions": instructions,
            "tools": [{"type": "function", **tool}] if tool else [],
            "tool_choice": "auto",
            "audio": {
                "input": {"transcription": {"model": TRANSCRIBE_MODEL}, "turn_detection": {"type": "semantic_vad"}},
                "output": {"voice": voice or VOICE},
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

    async def preview(self, settings):
        """The live model itself says a line, in the voice and manner set: what voice mode will sound like."""
        import websockets

        rules = f"{manner(settings)} {ACCENT['fi']} When asked to say a line, say exactly that line and nothing else."
        s = await self.realtime_key(rules, None, settings["voice"])
        pcm = bytearray()
        async with websockets.connect(s["url"], max_size=None) as ws:
            await ws.send(json.dumps({"setup": {"model": s["model"]}}))
            await asyncio.wait_for(ws.recv(), 15)
            await ws.send(json.dumps({"realtimeInput": {"text": f"Say this line: {PREVIEW_LINE}"}}))
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), 30))
                sc = m.get("serverContent", {})
                for p in sc.get("modelTurn", {}).get("parts", []):
                    if "inlineData" in p:
                        pcm += base64.b64decode(p["inlineData"]["data"])
                if sc.get("turnComplete"):
                    break
        return wav(bytes(pcm)), "audio/wav"

    async def realtime_key(self, instructions, tool, voice=None):
        import httpx

        def at(minutes):
            return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

        setup = {
            "model": GEMINI_MODEL,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice or GEMINI_VOICE}}},
            },
            "systemInstruction": {"parts": [{"text": instructions}]},
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
        }
        if tool:
            setup["tools"] = [{"functionDeclarations": [{**tool, "parameters": gemini_schema(tool["parameters"])}]}]
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

    async def preview(self, settings):
        self.previewed = settings
        return wav(bytes(20)), "audio/wav"

    async def realtime_key(self, instructions, tool, voice=None):
        self.session = {"instructions": instructions, "tools": [tool], "voice": voice}
        return {"engine": "openai", "key": "ek_fake", "model": "fake-realtime"}
