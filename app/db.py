"""SQLite, one file: notes and messages. v0 has exactly one board (ASSUMPTION: more boards later)."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from .models import Message, Note

SCHEMA = """
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
        self.conn.commit()

    # ---- notes -------------------------------------------------------------------------------

    def _note(self, row):
        d = dict(row)
        d["highlights"] = json.loads(d["highlights"])
        d["tags"] = json.loads(d["tags"])
        d["tape"] = bool(d["tape"])
        return Note(**d)

    def notes(self):
        rows = self.conn.execute("select * from notes order by created_at").fetchall()
        return [self._note(r) for r in rows]

    def note(self, note_id):
        row = self.conn.execute("select * from notes where id = ?", (note_id,)).fetchone()
        return self._note(row) if row else None

    def save_note(self, n: Note):
        self.conn.execute(
            """insert into notes (id, title, body, highlights, palette, font, sticker, tape, tags, x, y, rotation,
                                  created_at, updated_at, source_message_id)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               on conflict(id) do update set title=excluded.title, body=excluded.body, highlights=excluded.highlights,
                 palette=excluded.palette, font=excluded.font, sticker=excluded.sticker, tape=excluded.tape,
                 tags=excluded.tags, x=excluded.x, y=excluded.y, rotation=excluded.rotation,
                 updated_at=excluded.updated_at""",
            (n.id, n.title, n.body, json.dumps(n.highlights, ensure_ascii=False), n.palette, n.font, n.sticker, int(n.tape),
             json.dumps(n.tags, ensure_ascii=False), n.x, n.y, n.rotation, n.created_at, n.updated_at, n.source_message_id),
        )
        self.conn.commit()
        return n

    def delete_note(self, note_id):
        cur = self.conn.execute("delete from notes where id = ?", (note_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ---- messages ----------------------------------------------------------------------------

    def messages(self, limit=None):
        rows = self.conn.execute("select * from messages order by created_at, rowid").fetchall()
        out = [Message(**dict(r)) for r in rows]
        return out[-limit:] if limit else out

    def add_message(self, role, content):
        m = Message(id=new_id(), role=role, content=content, created_at=now())
        self.conn.execute("insert into messages values (?, ?, ?, ?)", (m.id, m.role, m.content, m.created_at))
        self.conn.commit()
        return m
