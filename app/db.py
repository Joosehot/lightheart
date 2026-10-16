"""SQLite, one file. Every idea is a board of its own: its notes, its chats (past chats kept), its comic books."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from .models import Message, Note

SCHEMA = """
create table if not exists boards (
  id text primary key,
  title text not null,
  created_at text not null,
  updated_at text not null
);
create table if not exists chats (
  id text primary key,
  board_id text not null,
  title text not null,
  created_at text not null,
  updated_at text not null
);
create table if not exists notes (
  id text primary key,
  title text not null default '',
  body text not null default '',
  highlights text not null default '[]',
  palette text not null,
  font text not null,
  sticker text,
  tape integer not null default 1,
  tags text not null default '[]',
  x real not null default 0,
  y real not null default 0,
  rotation real not null default 0,
  created_at text not null,
  updated_at text not null,
  source_message_id text
);
create table if not exists messages (
  id text primary key,
  role text not null,
  content text not null,
  created_at text not null
);
create table if not exists books (
  id text primary key,
  title text not null,
  characters text not null default '[]',
  direction text not null default '',
  created_at text not null
);
create table if not exists panels (
  id text primary key,
  book_id text not null references books(id) on delete cascade,
  page integer not null,
  idx integer not null,
  scene text not null,
  caption text not null default '',
  bubbles text not null default '[]',
  image text,
  status text not null default 'waiting',
  error text
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id():
    return str(uuid.uuid4())


class DB:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        # columns added after the first version: put into an older database file
        for table, col, decl in (("books", "art_style", "text not null default ''"), ("books", "world", "text not null default ''"),
                                 ("panels", "shot", "text not null default ''"), ("panels", "setting", "text not null default ''"),
                                 ("panels", "action", "text not null default ''"),
                                 ("notes", "board_id", "text"), ("messages", "chat_id", "text"), ("books", "board_id", "text")):
            have = {r["name"] for r in self.conn.execute(f"pragma table_info({table})")}
            if col not in have:
                self.conn.execute(f"alter table {table} add column {col} {decl}")
        self.conn.commit()
        # from the one-board version: whatever has no board goes to a first idea, its one chat
        orphans = any(self.conn.execute(f"select 1 from {t} where {c} is null limit 1").fetchone()
                      for t, c in (("notes", "board_id"), ("messages", "chat_id"), ("books", "board_id")))
        if orphans:
            b = self.add_board("My ideas", chat_title="First chat")
            chat = self.chats(b["id"])[0]
            self.conn.execute("update notes set board_id = ? where board_id is null", (b["id"],))
            self.conn.execute("update books set board_id = ? where board_id is null", (b["id"],))
            self.conn.execute("update messages set chat_id = ? where chat_id is null", (chat["id"],))
            self.conn.commit()

    # ---- boards (ideas) and chats ------------------------------------------------------------

    def boards(self):
        out = []
        for r in self.conn.execute("select * from boards order by updated_at desc").fetchall():
            b = dict(r)
            b["notes"] = self.conn.execute("select count(*) from notes where board_id = ?", (b["id"],)).fetchone()[0]
            b["chats"] = self.chats(b["id"])
            out.append(b)
        return out

    def board(self, board_id):
        r = self.conn.execute("select * from boards where id = ?", (board_id,)).fetchone()
        return dict(r) if r else None

    def add_board(self, title, chat_title="New chat"):
        t = now()
        b = {"id": new_id(), "title": title.strip()[:80] or "New idea", "created_at": t, "updated_at": t}
        self.conn.execute("insert into boards values (?, ?, ?, ?)", (b["id"], b["title"], t, t))
        self.conn.commit()
        self.add_chat(b["id"], chat_title)
        return b

    def default_board(self):
        """The idea worked on last (a first one when there is none)."""
        r = self.conn.execute("select * from boards order by updated_at desc limit 1").fetchone()
        return dict(r) if r else self.add_board("My ideas", chat_title="First chat")

    def rename_board(self, board_id, title):
        self.conn.execute("update boards set title = ? where id = ?", (title.strip()[:80] or "New idea", board_id))
        self.conn.commit()

    def touch_board(self, board_id):
        self.conn.execute("update boards set updated_at = ? where id = ?", (now(), board_id))
        self.conn.commit()

    def delete_board(self, board_id):
        for (bid,) in self.conn.execute("select id from books where board_id = ?", (board_id,)).fetchall():
            self.delete_book(bid)
        self.conn.execute("delete from messages where chat_id in (select id from chats where board_id = ?)", (board_id,))
        self.conn.execute("delete from chats where board_id = ?", (board_id,))
        self.conn.execute("delete from notes where board_id = ?", (board_id,))
        cur = self.conn.execute("delete from boards where id = ?", (board_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def chats(self, board_id):
        rows = self.conn.execute("select * from chats where board_id = ? order by updated_at desc", (board_id,)).fetchall()
        out = []
        for r in rows:
            c = dict(r)
            c["messages"] = self.conn.execute("select count(*) from messages where chat_id = ?", (c["id"],)).fetchone()[0]
            out.append(c)
        return out

    def chat(self, chat_id):
        r = self.conn.execute("select * from chats where id = ?", (chat_id,)).fetchone()
        return dict(r) if r else None

    def add_chat(self, board_id, title="New chat"):
        t = now()
        c = {"id": new_id(), "board_id": board_id, "title": title.strip()[:80] or "New chat", "created_at": t, "updated_at": t}
        self.conn.execute("insert into chats values (?, ?, ?, ?, ?)", (c["id"], board_id, c["title"], t, t))
        self.conn.commit()
        return c

    def rename_chat(self, chat_id, title):
        self.conn.execute("update chats set title = ? where id = ?", (title.strip()[:80] or "New chat", chat_id))
        self.conn.commit()

    def touch_chat(self, chat_id):
        self.conn.execute("update chats set updated_at = ? where id = ?", (now(), chat_id))
        self.conn.commit()

    def delete_chat(self, chat_id):
        self.conn.execute("delete from messages where chat_id = ?", (chat_id,))
        cur = self.conn.execute("delete from chats where id = ?", (chat_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ---- notes -------------------------------------------------------------------------------

    def _note(self, row):
        d = dict(row)
        d["highlights"] = json.loads(d["highlights"])
        d["tags"] = json.loads(d["tags"])
        d["tape"] = bool(d["tape"])
        return Note(**d)

    def notes(self, board_id=None):
        if board_id is None:
            rows = self.conn.execute("select * from notes order by created_at").fetchall()
        else:
            rows = self.conn.execute("select * from notes where board_id = ? order by created_at", (board_id,)).fetchall()
        return [self._note(r) for r in rows]

    def note(self, note_id):
        row = self.conn.execute("select * from notes where id = ?", (note_id,)).fetchone()
        return self._note(row) if row else None

    def save_note(self, n: Note):
        self.conn.execute(
            """insert into notes (id, title, body, highlights, palette, font, sticker, tape, tags, x, y, rotation,
                                  created_at, updated_at, source_message_id, board_id)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               on conflict(id) do update set title=excluded.title, body=excluded.body, highlights=excluded.highlights,
                 palette=excluded.palette, font=excluded.font, sticker=excluded.sticker, tape=excluded.tape,
                 tags=excluded.tags, x=excluded.x, y=excluded.y, rotation=excluded.rotation,
                 updated_at=excluded.updated_at""",
            (n.id, n.title, n.body, json.dumps(n.highlights, ensure_ascii=False), n.palette, n.font, n.sticker, int(n.tape),
             json.dumps(n.tags, ensure_ascii=False), n.x, n.y, n.rotation, n.created_at, n.updated_at, n.source_message_id, n.board_id),
        )
        self.conn.commit()
        return n

    def delete_note(self, note_id):
        cur = self.conn.execute("delete from notes where id = ?", (note_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ---- messages ----------------------------------------------------------------------------

    def messages(self, chat_id=None, limit=None):
        if chat_id is None:
            rows = self.conn.execute("select * from messages order by created_at, rowid").fetchall()
        else:
            rows = self.conn.execute("select * from messages where chat_id = ? order by created_at, rowid", (chat_id,)).fetchall()
        out = [Message(**dict(r)) for r in rows]
        return out[-limit:] if limit else out

    def add_message(self, role, content, chat_id=None):
        m = Message(id=new_id(), role=role, content=content, created_at=now(), chat_id=chat_id)
        self.conn.execute("insert into messages (id, role, content, created_at, chat_id) values (?, ?, ?, ?, ?)", (m.id, m.role, m.content, m.created_at, chat_id))
        self.conn.commit()
        return m

    # ---- comic books -------------------------------------------------------------------------

    def add_book(self, script, direction="", art_style="", board_id=None):
        bid = new_id()
        self.conn.execute("insert into books (id, title, characters, direction, created_at, art_style, world, board_id) values (?, ?, ?, ?, ?, ?, ?, ?)",
                          (bid, script.title, json.dumps(script.characters, ensure_ascii=False), direction, now(), art_style, script.world, board_id))
        for p, panels in enumerate(script.pages):
            for i, pn in enumerate(panels):
                self.conn.execute(
                    "insert into panels (id, book_id, page, idx, scene, caption, bubbles, shot, setting, action) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (new_id(), bid, p, i, pn["scene"], pn["caption"], json.dumps(pn["bubbles"], ensure_ascii=False), pn.get("shot", ""), pn.get("setting", ""), pn.get("action", "")),
                )
        self.conn.commit()
        return bid

    def _panel(self, row):
        d = dict(row)
        d["bubbles"] = json.loads(d["bubbles"])
        return d

    def book(self, book_id):
        row = self.conn.execute("select * from books where id = ?", (book_id,)).fetchone()
        if not row:
            return None
        b = dict(row)
        b["characters"] = json.loads(b["characters"])
        b["panels"] = [self._panel(r) for r in self.conn.execute("select * from panels where book_id = ? order by page, idx", (book_id,))]
        return b

    def books(self, board_id=None):
        out = []
        q = "select * from books order by created_at desc" if board_id is None else "select * from books where board_id = ? order by created_at desc"
        for r in self.conn.execute(q, () if board_id is None else (board_id,)).fetchall():
            cover = self.conn.execute("select image from panels where book_id = ? and image is not null order by page, idx limit 1", (r["id"],)).fetchone()
            counts = self.conn.execute("select count(*), sum(status = 'done') from panels where book_id = ?", (r["id"],)).fetchone()
            out.append({"id": r["id"], "title": r["title"], "created_at": r["created_at"], "cover": cover["image"] if cover else None, "panels": counts[0], "done": counts[1] or 0})
        return out

    def panel(self, panel_id):
        row = self.conn.execute("select * from panels where id = ?", (panel_id,)).fetchone()
        return self._panel(row) if row else None

    def set_panel(self, panel_id, **fields):
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"update panels set {cols} where id = ?", (*fields.values(), panel_id))
        self.conn.commit()

    def delete_book(self, book_id):
        self.conn.execute("delete from panels where book_id = ?", (book_id,))
        cur = self.conn.execute("delete from books where id = ?", (book_id,))
        self.conn.commit()
        return cur.rowcount > 0
