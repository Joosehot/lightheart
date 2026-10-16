"""The model's board operations, checked and applied. Nothing the model says is trusted as is:
a style outside the allowed lists is repaired, a bad op is skipped, nothing here ever raises."""

import logging
import math
import random

from . import styles
from .db import new_id, now
from .models import Note

log = logging.getLogger("lightheart.ops")

TEXT_FIELDS = ("title", "body")


def _words(text, limit):
    w = str(text).split()
    return " ".join(w[:limit]) + (" …" if len(w) > limit else "")


def clean_fields(fields, base=None):
    """Repair what a create or update gives. `base`: the note being updated (for highlights)."""
    out = {}
    if not isinstance(fields, dict):
        return out
    if "title" in fields and fields["title"] is not None:
        out["title"] = _words(fields["title"], styles.MAX_TITLE_WORDS).strip()
    if "body" in fields and fields["body"] is not None:
        out["body"] = _words(fields["body"], styles.MAX_BODY_WORDS).strip()
    if "palette" in fields:
        p = fields["palette"]
        out["palette"] = p if p in styles.PALETTES else styles.DEFAULT_PALETTE
    if "font" in fields:
        f = fields["font"]
        out["font"] = f if f in styles.FONTS else styles.DEFAULT_FONT
    if "sticker" in fields:
        s = fields["sticker"]
        out["sticker"] = s if s in styles.STICKERS else None
    if "tape" in fields:
        out["tape"] = bool(fields["tape"])
    if "tags" in fields and isinstance(fields["tags"], list):
        out["tags"] = [str(t)[:30] for t in fields["tags"] if str(t).strip()][:6]
    for k in ("x", "y", "rotation"):
        if k in fields and isinstance(fields[k], (int, float)) and math.isfinite(fields[k]):
            out[k] = float(fields[k])
    if "rotation" in out:
        out["rotation"] = max(-15.0, min(15.0, out["rotation"]))
    if "highlights" in fields and isinstance(fields["highlights"], list):
        body = out.get("body", base.body if base else "")
        # only phrases that are in the body, at most three
        hl = [str(h) for h in fields["highlights"] if isinstance(h, str) and h.strip() and h.strip() in body]
        out["highlights"] = hl[: styles.MAX_HIGHLIGHTS]
    return out


def free_spot(notes):
    """A free place near the centre top: a spiral search that avoids every card already there."""
    w, h = styles.CARD_W, styles.CARD_H
    cx, cy = styles.BOARD_W / 2 - w / 2, 40

    def free(x, y):
        return all(abs(n.x - x) >= w + 16 or abs(n.y - y) >= h + 16 for n in notes)

    for r in range(0, 4000, 40):
        steps = max(1, int(2 * math.pi * r / 60))
        for i in range(steps):
            a = math.pi / 2 + 2 * math.pi * i / steps  # start straight below the centre top
            x, y = cx + r * math.cos(a) * 1.6, cy + r * math.sin(a)
            if x >= 0 and y >= 0 and free(x, y):
                return x, y
    return cx, cy + 40 * len(notes)


def new_note(fields, notes, source_message_id=None, rng=random, board_id=None):
    f = clean_fields(fields)
    x, y = free_spot(notes)
    t = now()
    return Note(
        id=new_id(),
        title=f.get("title", ""),
        body=f.get("body", ""),
        highlights=f.get("highlights", []),
        palette=f.get("palette", styles.DEFAULT_PALETTE),
        font=f.get("font", styles.DEFAULT_FONT),
        sticker=f.get("sticker"),
        tape=f.get("tape", True),
        tags=f.get("tags", []),
        x=f.get("x", x),
        y=f.get("y", y),
        rotation=f.get("rotation", round(rng.uniform(-3, 3), 1)),
        created_at=t,
        updated_at=t,
        source_message_id=source_message_id,
        board_id=board_id,
    )


def updated(note, fields):
    f = clean_fields(fields, base=note)
    data = note.model_dump()
    data.update(f)
    # a highlight no longer in the body goes
    data["highlights"] = [h for h in data["highlights"] if h in data["body"]][: styles.MAX_HIGHLIGHTS]
    data["updated_at"] = now()
    return Note(**data)


def apply(db, ops, source_message_id=None, board_id=None):
    """Apply the model's ops to the board; return the notes made or changed. Never raises."""
    changed = []
    if not isinstance(ops, list):
        log.warning("ops is not a list: %r", type(ops))
        return changed
    real = [o for o in ops if isinstance(o, dict) and o.get("op") in ("create", "update")]
    if len(real) > styles.MAX_OPS_PER_TURN:
        log.warning("%d ops, keeping %d", len(real), styles.MAX_OPS_PER_TURN)
    for op in real[: styles.MAX_OPS_PER_TURN]:
        try:
            if op["op"] == "create":
                fields = op.get("note") if isinstance(op.get("note"), dict) else {}
                if not (str(fields.get("title") or "").strip() or str(fields.get("body") or "").strip()):
                    log.warning("an empty card, skipped")
                    continue
                n = new_note(fields, db.notes(board_id), source_message_id, board_id=board_id)
                changed.append(db.save_note(n))
            else:
                note = db.note(str(op.get("id") or ""))
                if note is None or (board_id is not None and note.board_id != board_id):
                    log.warning("update of an unknown card %r, skipped", op.get("id"))
                    continue
                changed.append(db.save_note(updated(note, op.get("fields") or {})))
        except Exception:
            log.exception("a bad op, skipped: %r", op)
    return changed


def board_state(notes):
    """The compact board the model sees: id, title, tags, the first ~120 characters of the body."""
    return [{"id": n.id, "title": n.title, "tags": n.tags, "body": n.body[:120]} for n in notes]
