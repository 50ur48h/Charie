"""POST /api/knowledge/{key}/suggest: a correction for the learner (P12.2)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.knowledge.store import get_entry
from charie.shared.knowledge.todos import add_learner_todo
from charie.shared.knowledge.versions import get_published

suggest_router = APIRouter()


class SuggestBody(BaseModel):
    text: str


@suggest_router.post("/api/knowledge/{key}/suggest", status_code=201)
def suggest_change(key: str, body: SuggestBody, session: Session = Depends(get_session)) -> dict:
    """Queue a correction to-do; the published entry never rewrites."""
    text = (body.text or "").strip()
    if not text:
        raise ApiError(400, "empty_text", "Write your suggestion first.")
    published = get_published(session)
    entry = get_entry(session, published.id, key) if published is not None else None
    if entry is None:
        raise ApiError(404, "not_found", f"There\u2019s no knowledge entry called {key}.")
    todo_id = add_learner_todo(
        session,
        "correction",
        text,
        {
            "entry_key": key,
            "entry_title": entry.title,
            "kb_version": published.number,
            "words": len(text.split()),
        },
    )
    session.commit()
    return {"todo_id": todo_id}
