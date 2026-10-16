import os

os.environ["LIGHTHEART_NO_APP"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app import comics  # noqa: E402
from app.llm.base import FakeProvider  # noqa: E402
from app.main import create_app  # noqa: E402


def make(tmp_path, writer=None, maker=None):
    app = create_app(provider=FakeProvider([]), db_path=str(tmp_path / "t.db"), writer=writer or comics.FakeScriptWriter(),
                     maker=maker or comics.FakeImageMaker(), image_dir=str(tmp_path / "img"), draw_now=True)
    c = TestClient(app)
    c.post("/api/notes", json={"title": "Majakanvartija", "body": "Vastaa hukkuneisiin kirjeisiin eri nimellä."})
    return c, app


def test_a_book_from_the_board(tmp_path):
    writer, maker = comics.FakeScriptWriter(), comics.FakeImageMaker()
    c, _ = make(tmp_path, writer, maker)
    r = c.post("/api/books", json={"pages": 2, "direction": "iltasatu"})
    assert r.status_code == 200
    b = r.json()
    assert b["title"] == "Testikirja" and len(b["panels"]) == 6
    # every panel drawn, every picture there, the character's look in its prompt and no words asked for
    b = c.get(f"/api/books/{b['id']}").json()
    assert all(p["status"] == "done" and p["image"] for p in b["panels"])
    assert c.get(f"/images/{b['panels'][0]['image']}").status_code == 200
    assert all("yellow raincoat" in p and "No text" in p for p in maker.prompts)
    # the board's cards went to the writer, with the wish
    ideas, direction, pages = writer.calls[0]
    assert "Majakanvartija" in ideas and direction == "iltasatu" and pages == 2
    shelf = c.get("/api/books").json()
    assert shelf[0]["done"] == 6 and shelf[0]["cover"]


def test_script_limits_are_kept():
    data = {"title": "x" * 300, "characters": [{"name": "A", "look": "l"}, {"bad": 1}],
            "pages": [{"panels": [{"scene": "s", "bubbles": [{"speaker": "A", "text": "1"}, {"speaker": "A", "text": "2"}, {"speaker": "A", "text": "3"}]}] * 9}] * 10}
    s = comics.clean_script(data, pages=3)
    assert len(s.title) <= 80 and len(s.characters) == 1
    assert len(s.pages) == 3 and all(len(p) <= comics.PANELS_PER_PAGE for p in s.pages)
    assert all(len(pn["bubbles"]) <= comics.MAX_BUBBLES for p in s.pages for pn in p)
    assert comics.clean_script(None, 3) is None
    assert comics.clean_script({"title": "t", "pages": [{"panels": [{"scene": ""}]}]}, 3) is None


def test_a_failed_picture_can_be_redrawn(tmp_path):
    class Flaky(comics.FakeImageMaker):
        def __init__(self):
            super().__init__()
            self.fail = True

        async def draw(self, prompt):
            if self.fail:
                raise RuntimeError("busy")
            return await super().draw(prompt)

    maker = Flaky()
    c, _ = make(tmp_path, maker=maker)
    b = c.post("/api/books", json={"pages": 1}).json()
    assert all(p["status"] == "failed" for p in c.get(f"/api/books/{b['id']}").json()["panels"])
    maker.fail = False
    pid = b["panels"][0]["id"]
    assert c.post(f"/api/panels/{pid}/redraw").json()["status"] == "done"


def test_no_keys_no_book(tmp_path):
    app = create_app(provider=FakeProvider([]), db_path=str(tmp_path / "t.db"), writer=None, maker=None, image_dir=str(tmp_path / "img"))
    app.state.writer = None
    app.state.maker = None
    c = TestClient(app)
    r = c.post("/api/books", json={"pages": 2, "direction": "a story"})
    assert r.status_code == 400 and "API_KEY" in r.json()["detail"]


def test_estimate_and_delete(tmp_path):
    c, _ = make(tmp_path)
    e = c.get("/api/books/estimate?pages=6").json()
    assert e["images"] == 18 and e["usd"] < 1
    b = c.post("/api/books", json={"pages": 1}).json()
    img = tmp_path / "img" / c.get(f"/api/books/{b['id']}").json()["panels"][0]["image"]
    assert img.exists()
    assert c.delete(f"/api/books/{b['id']}").status_code == 200
    assert not img.exists() and c.get("/api/books").json() == []
