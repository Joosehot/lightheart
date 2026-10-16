# Lightheart (v0)

Talk to an AI about your ideas; they appear as scrapbook notes on a board that stays.

    powershell -File scripts/set-key.ps1       # once: your Anthropic API key, kept in .env
    uvicorn app.main:app --reload              # then open http://127.0.0.1:8000/

- Chat model: `LIGHTHEART_MODEL` (default Haiku 4.5). Database: `LIGHTHEART_DB` (default `lightheart.db`).
- Comic book (📖): the story by `LIGHTHEART_STORY_MODEL` (default Sonnet 5.5), pictures by OpenAI `gpt-image-2` (`OPENAI_API_KEY` in .env; `LIGHTHEART_IMAGE_QUALITY` low/medium/high, low ≈ $0.006 a picture).
- Allowed palettes, fonts and stickers: `app/styles.py` (the only source).
- Tests (no network): `python -m pytest`. Live smoke test: `LIGHTHEART_LIVE=1` with a key set.
- `GET /api/export` gives the whole board as JSON.
