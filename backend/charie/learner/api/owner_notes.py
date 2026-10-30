"""The owner's notes: read them, save them, and how Charie sorted them (P07.5)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.knowledge.store import list_entries
from charie.shared.knowledge.versions import get_draft, get_published
from charie.shared.tables.sources import OwnerNote

owner_notes_router = APIRouter()

TEXT_MAX = 100_000


class PutNotesIn(BaseModel):
    text: str


def _lines(text: str) -> int:
    """Non-empty lines."""
    return sum(1 for line in text.splitlines() if line.strip())


def _sorted_lists(session: Session) -> dict | None:
    """The last sort: {key, title} items from owner-notes entries.

    Rules become hard rules, styles become style, every other kind is a
    hint. The draft's entries win; without a draft the published ones do.
    """
    version = get_draft(session) or get_published(session)
    if version is None:
        return None
    hard_rules: list[dict] = []
    style: list[dict] = []
    hints: list[dict] = []
    for entry in list_entries(session, version.id):
        if not any(source.get("type") == "owner_notes" for source in entry.sources):
            continue
        item = {"key": entry.key, "title": entry.title}
        if entry.kind == "rule":
            hard_rules.append(item)
        elif entry.kind == "style":
            style.append(item)
        else:
            hints.append(item)
    return {"hard_rules": hard_rules, "style": style, "hints": hints}


def _shape(note: OwnerNote | None, session: Session) -> dict:
    """The GET answer; blank notes read as never written."""
    if note is None or not note.text_.strip():
        return {"text": "", "saved_at": None, "lines": 0, "sorted": None, "sorted_at": None}
    return {
        "text": note.text_,
        "saved_at": note.saved_at.isoformat() if note.saved_at else None,
        "lines": _lines(note.text_),
        "sorted": _sorted_lists(session),
        "sorted_at": note.sorted_at.isoformat() if note.sorted_at else None,
    }


def _newest(session: Session) -> OwnerNote | None:
    """The current notes: the newest row."""
    return session.scalar(select(OwnerNote).order_by(OwnerNote.id.desc()).limit(1))


@owner_notes_router.get("/api/owner-notes")
def get_owner_notes(session: Session = Depends(get_session)) -> dict:
    """The notes, how many lines, and the last sorting."""
    return _shape(_newest(session), session)


@owner_notes_router.put("/api/owner-notes")
def put_owner_notes(body: PutNotesIn, session: Session = Depends(get_session)) -> dict:
    """Save the notes; a new row only when the text changed."""
    if len(body.text) > TEXT_MAX:
        raise ApiError(
            400,
            "notes_too_long",
            "Your notes are too long. Keep them under 100,000 characters.",
        )
    current = _newest(session)
    before = current.text_ if current is not None else ""
    if before != body.text:
        session.add(OwnerNote(text_=body.text))
        session.commit()
    return _shape(_newest(session), session)
