import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["LIGHTHEART_NO_APP"] = "1"  # tests build their own app

from app import ops, styles  # noqa: E402
from app.db import DB  # noqa: E402
from app.llm.base import AIResult, FakeProvider  # noqa: E402
from app.main import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

IDEA = AIResult(
    reply="A lighthouse keeper answering lost letters: lovely. Who wrote the first one?",
    ops=[{"op": "create", "note": {
        "title": "The keeper of lost letters",
        "body": "A lighthouse keeper collects letters the sea brings and answers each one under a new name.",
        "highlights": ["answers each one", "under a new name"],
        "palette": "sky", "font": "caveat", "sticker": "moon", "tape": True, "tags": ["story", "character"],
    }}],
)
SMALL_TALK = AIResult(reply="Hi! What are you working on today?", ops=[{"op": "none"}])


def make(script, tmp_path):
    provider = FakeProvider(script)
    app = create_app(provider=provider, db_path=str(tmp_path / "t.db"))
    return TestClient(app), provider


def test_page_and_board_load(tmp_path):
    c, _ = make([], tmp_path)
    r = c.get("/")
    assert r.status_code == 200 and "Lightheart" in r.text
    assert c.get("/static/app.js").status_code == 200
    assert c.get("/static/style.css").status_code == 200
    b = c.get("/api/board").json()
    assert b["notes"] == [] and b["messages"] == [] and b["board"]["title"] and b["chat"]["id"]


def test_ideas_have_their_own_boards_and_past_chats(tmp_path):
    c, provider = make(lambda m, s: IDEA if "lighthouse" in m[-1]["content"] else SMALL_TALK, tmp_path)
    first = c.get("/api/board").json()
    c.post("/api/chat", json={"content": "a lighthouse keeper", "board_id": first["board"]["id"], "chat_id": first["chat"]["id"]})
    # a second idea: its own empty board and chat
    second = c.post("/api/boards", json={"title": "Space cat"}).json()
    b2 = c.get(f"/api/board?board_id={second['board']['id']}").json()
    assert b2["notes"] == [] and b2["messages"] == [] and b2["board"]["title"] == "Space cat"
    c.post("/api/chat", json={"content": "hi there", "board_id": second["board"]["id"], "chat_id": second["chat"]["id"]})
    # the model only saw the second idea's cards (none)
    assert provider.calls[-1][1] == []
    # a new chat in the first idea; the past one is still there, named by its first message
    new = c.post(f"/api/boards/{first['board']['id']}/chats").json()
    chats = {ch["id"]: ch for ch in next(b for b in c.get("/api/boards").json() if b["id"] == first["board"]["id"])["chats"]}
    assert first["chat"]["id"] in chats and new["id"] in chats
    assert chats[first["chat"]["id"]]["title"] == "a lighthouse keeper" and chats[first["chat"]["id"]]["messages"] == 2
    past = c.get(f"/api/board?board_id={first['board']['id']}&chat_id={first['chat']['id']}").json()
    assert len(past["messages"]) == 2 and len(past["notes"]) == 1
    fresh = c.get(f"/api/board?board_id={first['board']['id']}&chat_id={new['id']}").json()
    assert fresh["messages"] == [] and len(fresh["notes"]) == 1  # same idea, same cards
    # rename, delete
    assert c.patch(f"/api/boards/{second['board']['id']}", json={"title": "Avaruuskissa"}).json()["title"] == "Avaruuskissa"
    assert c.delete(f"/api/chats/{new['id']}").status_code == 200
    assert c.delete(f"/api/boards/{second['board']['id']}").status_code == 200
    assert [b["title"] for b in c.get("/api/boards").json()] == [first["board"]["title"]]


def test_an_old_one_board_database_becomes_a_first_idea(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""create table notes (id text primary key, title text not null default '', body text not null default '', highlights text not null default '[]',
        palette text not null, font text not null, sticker text, tape integer not null default 1, tags text not null default '[]', x real not null default 0,
        y real not null default 0, rotation real not null default 0, created_at text not null, updated_at text not null, source_message_id text);
      create table messages (id text primary key, role text not null, content text not null, created_at text not null);
      insert into notes (id, title, palette, font, created_at, updated_at) values ('n1', 'Old idea', 'sky', 'caveat', '2026', '2026');
      insert into messages values ('m1', 'user', 'hello', '2026');""")
    con.commit()
    con.close()
    app = create_app(provider=FakeProvider([]), db_path=str(path))
    b = TestClient(app).get("/api/board").json()
    assert b["board"]["title"] == "My ideas" and b["chat"]["title"] == "First chat"
    assert [n["title"] for n in b["notes"]] == ["Old idea"] and [m["content"] for m in b["messages"]] == ["hello"]


def test_idea_makes_a_card_small_talk_none(tmp_path):
    c, _ = make([SMALL_TALK, IDEA], tmp_path)
    r = c.post("/api/chat", json={"content": "hello"}).json()
    assert r["reply"] and r["notes_changed"] == []
    r = c.post("/api/chat", json={"content": "a lighthouse keeper who answers lost letters"}).json()
    assert len(r["notes_changed"]) == 1
    n = r["notes_changed"][0]
    assert n["palette"] == "sky" and n["sticker"] == "moon" and n["highlights"] == ["answers each one", "under a new name"]
    board = c.get("/api/board").json()
    assert len(board["notes"]) == 1 and len(board["messages"]) == 4


def test_follow_up_updates_instead_of_duplicating(tmp_path):
    def script(messages, board_state):
        if not board_state:
            return IDEA
        # the model sees the card and updates it
        return AIResult(reply="Yes, and the first letter is from her own future self.",
                        ops=[{"op": "update", "id": board_state[0]["id"], "fields": {"body": "A lighthouse keeper answers lost letters under new names; the first came from her future self.", "highlights": ["her future self"]}}])

    c, provider = make(script, tmp_path)
    c.post("/api/chat", json={"content": "a lighthouse keeper who answers lost letters"})
    r = c.post("/api/chat", json={"content": "what if the first letter is from herself, from the future?"}).json()
    notes = c.get("/api/board").json()["notes"]
    assert len(notes) == 1
    assert "future self" in notes[0]["body"] and notes[0]["highlights"] == ["her future self"]
    assert r["notes_changed"][0]["id"] == notes[0]["id"]
    # the model was shown the existing card compactly
    assert provider.calls[1][1][0]["title"] == "The keeper of lost letters"


def test_styles_outside_the_lists_are_repaired():
    f = ops.clean_fields({"palette": "neon-green", "font": "Comic Sans", "sticker": "<script>", "title": "a b c d e f g h i", "body": "x " * 100, "highlights": ["nope", "x", "x", "x", "x"]})
    assert f["palette"] == styles.DEFAULT_PALETTE
    assert f["font"] == styles.DEFAULT_FONT
    assert f["sticker"] is None
    assert len(f["title"].split()) <= styles.MAX_TITLE_WORDS + 1
    assert len(f["body"].split()) <= styles.MAX_BODY_WORDS + 1
    assert len(f["highlights"]) <= styles.MAX_HIGHLIGHTS and "nope" not in f["highlights"]


def test_bad_styles_from_the_model_never_reach_the_board(tmp_path):
    bad = AIResult(reply="ok", ops=[{"op": "create", "note": {"title": "T", "body": "B", "palette": "#ff00ff", "font": "x", "sticker": "skull"}}])
    c, _ = make([bad], tmp_path)
    n = c.post("/api/chat", json={"content": "idea"}).json()["notes_changed"][0]
    assert n["palette"] in styles.PALETTES and n["font"] in styles.FONTS and n["sticker"] is None


@pytest.mark.parametrize("result", [
    AIResult(reply="", ops=[], error="no tool call"),
    AIResult(reply="just text, no tool", ops=[], error="no tool call"),
    AIResult(reply="weird", ops="not a list"),
    AIResult(reply="weird", ops=[None, 3, {"op": "create"}, {"op": "update", "id": "nope", "fields": {}}, {"op": "explode"}]),
])
def test_malformed_model_output_does_not_break(tmp_path, result):
    c, _ = make([result], tmp_path)
    r = c.post("/api/chat", json={"content": "an idea"})
    assert r.status_code == 200
    body = r.json()
    assert body["notes_changed"] == []
    assert body["reply"]  # the reply text, or a gentle fallback
    assert c.get("/api/board").status_code == 200


def test_a_provider_that_raises_does_not_break(tmp_path):
    def boom(messages, board_state):
        raise RuntimeError("network down")

    c, _ = make(boom, tmp_path)
    r = c.post("/api/chat", json={"content": "an idea"})
    assert r.status_code == 200 and r.json()["notes_changed"] == []


def test_ops_capped_per_turn(tmp_path):
    many = AIResult(reply="lots", ops=[{"op": "create", "note": {"title": f"Idea {i}", "body": "b"}} for i in range(6)])
    c, _ = make([many], tmp_path)
    assert len(c.post("/api/chat", json={"content": "x"}).json()["notes_changed"]) == styles.MAX_OPS_PER_TURN


def test_manual_edits_persist(tmp_path):
    db_path = str(tmp_path / "t.db")
    c = TestClient(create_app(provider=FakeProvider([IDEA]), db_path=db_path))
    nid = c.post("/api/chat", json={"content": "idea"}).json()["notes_changed"][0]["id"]
    c.patch(f"/api/notes/{nid}", json={"x": 512, "y": 300, "rotation": 2.5, "title": "Lost letters", "palette": "rose", "font": "kalam", "sticker": None, "tape": False})
    blank = c.post("/api/notes", json={}).json()
    c.delete(f"/api/notes/{blank['id']}")
    # a fresh app on the same file: everything is still there
    c2 = TestClient(create_app(provider=FakeProvider([]), db_path=db_path))
    notes = c2.get("/api/board").json()["notes"]
    assert len(notes) == 1
    n = notes[0]
    assert (n["x"], n["y"], n["rotation"], n["title"], n["palette"], n["font"], n["sticker"], n["tape"]) == (512, 300, 2.5, "Lost letters", "rose", "kalam", None, False)
    # a manual patch is repaired too
    assert c2.patch(f"/api/notes/{nid}", json={"palette": "nope"}).json()["palette"] == styles.DEFAULT_PALETTE
    assert c2.delete("/api/notes/nope").status_code == 404


def test_new_cards_do_not_overlap(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    for i in range(12):
        db.save_note(ops.new_note({"title": f"n{i}"}, db.notes()))
    ns = db.notes()
    for i, a in enumerate(ns):
        for b in ns[i + 1:]:
            assert abs(a.x - b.x) >= styles.CARD_W or abs(a.y - b.y) >= styles.CARD_H


def test_export_is_valid_json(tmp_path):
    c, _ = make([IDEA], tmp_path)
    c.post("/api/chat", json={"content": "idea"})
    data = json.loads(c.get("/api/export").text)
    assert data["app"] == "lightheart" and len(data["notes"]) == 1 and len(data["messages"]) == 2


def test_no_api_key_in_the_frontend(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-secret-123")
    for f in (ROOT / "static").iterdir():
        text = f.read_text(encoding="utf-8")
        assert "ANTHROPIC_API_KEY" not in text and "sk-ant" not in text
    c, _ = make([IDEA], tmp_path)
    for path in ("/", "/api/board", "/api/styles", "/api/export", "/static/app.js"):
        assert "sk-ant-test-secret-123" not in c.get(path).text
    assert "sk-ant-test-secret-123" not in c.post("/api/chat", json={"content": "x"}).text


@pytest.mark.skipif(os.environ.get("LIGHTHEART_LIVE") != "1" or not os.environ.get("ANTHROPIC_API_KEY"), reason="live API test: set LIGHTHEART_LIVE=1 and ANTHROPIC_API_KEY")
def test_live_smoke(tmp_path):
    from app.llm.anthropic import AnthropicProvider

    c = TestClient(create_app(provider=AnthropicProvider(), db_path=str(tmp_path / "t.db")))
    r = c.post("/api/chat", json={"content": "Majakanvartija, joka vastaa hukkuneisiin kirjeisiin aina eri nimellä."}).json()
    assert r["reply"]
    print("reply:", r["reply"], "cards:", [(n["title"], n["palette"]) for n in r["notes_changed"]])


def test_voice_transcribes_and_speaks(tmp_path):
    from app.voice import FakeVoice

    voice = FakeVoice(heard="majakanvartija")
    c = TestClient(create_app(provider=FakeProvider([]), db_path=str(tmp_path / "t.db"), voice=voice))
    assert c.get("/api/voice").json() == {"engine": "openai"}
    r = c.post("/api/voice/transcribe", files={"audio": ("speech.webm", b"\x1aE\xdf\xa3fake", "audio/webm")}, data={"lang": "fi"})
    assert r.json() == {"text": "majakanvartija"}
    s = c.post("/api/voice/speak", json={"text": "Hei!", "lang": "fi"})
    assert s.status_code == 200 and s.headers["content-type"] == "audio/mpeg" and voice.spoken == ["Hei!"]


def test_no_openai_key_means_browser_voice(tmp_path):
    app = create_app(provider=FakeProvider([]), db_path=str(tmp_path / "t.db"))
    app.state.voice = None
    c = TestClient(app)
    assert c.get("/api/voice").json() == {"engine": "browser"}
    assert c.post("/api/voice/speak", json={"text": "x"}).status_code == 400
