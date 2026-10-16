# Lightheart

Talk with an AI about your ideas, by typing or out loud, and they turn into a scrapbook board of
colourful notes that stays. When an idea has grown, Lightheart can turn it into a short comic
book you can read, with real pictures.

- **Chat → notes.** Claude answers briefly and puts what has formed on the board as cards:
  highlights, washi tape, stickers, a palette that fits the mood. One idea can become several
  sticky notes. Cards can be dragged, edited and restyled by hand.
- **Ideas and past chats.** Every idea has its own board and its own chats; the sidebar keeps them.
- **Views.** Scrapbook (free-form board), Post-it (bright sticky notes in a grid) and Notes (a plain list).
- **Comic book.** Pick which notes, describe the story and the art style (watercolour, manga, ligne
  claire, noir, picture book, or your own words); Claude writes the script and OpenAI's
  `gpt-image-2` draws the panels.
- **Voice mode.** One button: a live voice model hears you, answers aloud, can be interrupted and
  puts cards on the board while you talk. Pick the voice, how it talks (warm friend, comic
  narrator, cartoon sidekick, superhero, noir detective, picture-book reader, or your own
  character) and the pace, and listen to a sample first.

Plain FastAPI + SQLite on the server, plain HTML/CSS/JS in the browser: no build step.

## Run it

Python 3.11+.

    pip install -r requirements.txt
    cp .env.example .env        # then fill in your keys (or: powershell -File scripts/set-key.ps1)
    uvicorn app.main:app        # open http://127.0.0.1:8000/

| Key | What for | Needed |
|---|---|---|
| `ANTHROPIC_API_KEY` | the chat (Claude Haiku 4.5) and the comic script (Sonnet 5.5) | yes |
| `OPENAI_API_KEY` | comic pictures (`gpt-image-2`, low quality ≈ $0.006 a picture) | for comics |
| `GEMINI_API_KEY` | voice mode on Gemini Live (`gemini-3.8-live`, about 1-3 cents a minute) | for voice |

Without a Gemini key, voice mode uses OpenAI's realtime voice if an OpenAI key is set (about 5-15
cents a minute), and otherwise the browser's own free speech. Every other setting is in
`.env.example`.

Your keys stay on the server: the browser only ever gets short-lived, single-use voice tokens.
Everything you write is kept in a local SQLite file (`lightheart.db`); `GET /api/export` gives all
of it as JSON.

## Code

- `app/main.py`: the API. `app/db.py`: SQLite. `app/ops.py`: the model's board operations, checked
  before they touch the board. `app/styles.py`: the allowed palettes, fonts and stickers (the only
  source; the prompt and the tool schema are built from it).
- `app/llm/`: the chat model, with tool use for structured output. `app/comics.py`: the comic
  book. `app/voice.py`: voice mode and its voices.
- `static/`: the page, no framework.
- Tests (no network): `python -m pytest`. A live smoke test runs with `LIGHTHEART_LIVE=1` and a key.

## License

MIT
