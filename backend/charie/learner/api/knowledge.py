"""Fixing and approving entries in the Learner, and its to-check list (P07.4).

`PATCH /api/knowledge/{key}` edits the draft, `POST …/approve` confirms
an entry, and `POST …/wrong` queues a correction to-do without touching
the entries. `GET /api/todos` lists the open to-dos, newest first.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette import status

from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.knowledge.store import (
    approve_entry,
    edit_entry,
    entry_to_dict,
    get_entry,
)
from charie.shared.knowledge.versions import get_draft, get_or_create_draft, get_published
from charie.shared.tables.questions import LearnerTodo

knowledge_router = APIRouter()

TITLE_MAX = 200
MEANING_MAX = 2000


class PatchEntryIn(BaseModel):
    title: str | None = None
    meaning: str | None = None


class MarkWrongIn(BaseModel):
    note: str | None = None


def _todo_shape(todo: LearnerTodo) -> dict:
    """One to-check row as the screens expect it."""
    return {
        "id": todo.id,
        "kind": todo.kind,
        "text": todo.text_,
        "details": todo.details,
        "status": todo.status,
        "result": todo.result,
        "created_at": todo.created_at.isoformat() if todo.created_at else None,
        "done_at": todo.done_at.isoformat() if todo.done_at else None,
    }


def _draft_or_published_entry(session: Session, key: str):
    """The entry the Learner would fix: from the draft, else the published one."""
    draft = get_draft(session)
    if draft is not None:
        entry = get_entry(session, draft.id, key)
        if entry is not None:
            return entry, draft.number
    published = get_published(session)
    if published is not None:
        entry = get_entry(session, published.id, key)
        if entry is not None:
            return entry, published.number
    return None, None


@knowledge_router.get("/api/todos")
def get_todos(session: Session = Depends(get_session)) -> dict:
    """The open to-dos, newest first."""
    todos = session.scalars(
        select(LearnerTodo).where(LearnerTodo.status == "open").order_by(LearnerTodo.id.desc())
    ).all()
    return {"todos": [_todo_shape(todo) for todo in todos]}


@knowledge_router.patch("/api/knowledge/{key}")
def patch_entry(key: str, body: PatchEntryIn, session: Session = Depends(get_session)) -> dict:
    """Edit the title and/or meaning in the draft; answers the updated entry."""
    title = body.title.strip() if isinstance(body.title, str) else None
    meaning = body.meaning.strip() if isinstance(body.meaning, str) else None
    if title is None and meaning is None:
        raise ApiError(400, "empty_edit", "Change the title or the meaning first.")
    if body.title is not None and not title:
        raise ApiError(400, "empty_title", "The title can't be empty.")
    if title is not None and len(title) > TITLE_MAX:
        raise ApiError(
            400, "title_too_long", "The title is too long. Keep it under 200 characters."
        )
    if body.meaning is not None and not meaning:
        raise ApiError(400, "empty_meaning", "The entry still needs a meaning.")
    if meaning is not None and len(meaning) > MEANING_MAX:
        raise ApiError(
            400,
            "meaning_too_long",
            "The meaning is too long. Keep it under 2,000 characters.",
        )
    entry, _ = _draft_or_published_entry(session, key)
    if entry is None:
        raise ApiError(404, "not_found", f"There's no knowledge entry called {key}.")
    draft = get_or_create_draft(session, "owner_edit")
    edit_entry(session, draft.id, key, title=title, meaning=meaning)
    updated = get_entry(session, draft.id, key)
    assert updated is not None
    session.commit()
    return {"entry": entry_to_dict(updated)}


@knowledge_router.post("/api/knowledge/{key}/approve")
def approve_knowledge_entry(key: str, session: Session = Depends(get_session)) -> dict:
    """Confirm an entry; already-confirmed entries have nothing to approve."""
    entry, _ = _draft_or_published_entry(session, key)
    if entry is None:
        raise ApiError(404, "not_found", f"There's no knowledge entry called {key}.")
    if entry.confidence == "confirmed":
        raise ApiError(409, "nothing_to_approve", "This entry is already confirmed by you.")
    draft = get_or_create_draft(session, "owner_edit")
    assert approve_entry(session, draft.id, key)
    updated = get_entry(session, draft.id, key)
    assert updated is not None
    session.commit()
    return {"entry": entry_to_dict(updated)}


@knowledge_router.post("/api/knowledge/{key}/wrong", status_code=status.HTTP_201_CREATED)
def mark_knowledge_wrong(
    key: str, body: MarkWrongIn, session: Session = Depends(get_session)
) -> dict:
    """Queue a correction to-do; the entry and the draft stay untouched."""
    entry, version_number = _draft_or_published_entry(session, key)
    if entry is None:
        raise ApiError(404, "not_found", f"There's no knowledge entry called {key}.")
    note = body.note.strip() if isinstance(body.note, str) and body.note.strip() else None
    todo = LearnerTodo(
        kind="correction",
        text_=f"{entry.title}: {note}" if note else f"{entry.title}: marked as wrong",
        details={"chat_title": None, "words": note, "key": key, "version": version_number},
        status="open",
    )
    session.add(todo)
    session.flush()
    shape = _todo_shape(todo)
    session.commit()
    return {"todo": shape}
