"""`GET /api/setup`: the setup guide's state (P04.2's `SetupState`)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.shared.db import get_session
from charie.shared.settings import get_setting
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import OwnerQuestion
from charie.shared.tables.sources import DataSource, Document, OwnerNote

setup_router = APIRouter()


class SetupState(BaseModel):
    setup_done: bool
    step: int
    readiness: None = None


def connected_source(session: Session) -> bool:
    """A source is saved and connected."""
    row = session.scalar(select(DataSource).where(DataSource.status == "connected").limit(1))
    return row is not None


def first_run(session: Session) -> LearningRun | None:
    """The newest `first` learning run, if any."""
    return session.scalar(
        select(LearningRun)
        .where(LearningRun.kind == "first")
        .order_by(LearningRun.id.desc())
        .limit(1)
    )


def has_documents(session: Session) -> bool:
    """A document that isn't removed."""
    return session.scalar(select(Document).where(Document.status != "removed").limit(1)) is not None


def has_notes(session: Session) -> bool:
    """A saved owner note."""
    return session.scalar(select(OwnerNote).limit(1)) is not None


def has_waiting_questions(session: Session) -> bool:
    """An owner question still waiting."""
    return (
        session.scalar(select(OwnerQuestion).where(OwnerQuestion.status == "waiting").limit(1))
        is not None
    )


def setup_step(session: Session) -> int:
    """The first setup step that isn't complete (P04.2's rule)."""
    if not connected_source(session):
        return 1
    run = first_run(session)
    if run is None and not has_documents(session) and not has_notes(session):
        return 2
    if run is None or run.status != "done":
        return 3
    if has_waiting_questions(session):
        return 4
    return 5


@setup_router.get("/api/setup", response_model=SetupState)
def get_setup(session: Session = Depends(get_session)) -> dict[str, object]:
    return {
        "setup_done": bool(get_setting(session, "setup_done")),
        "step": setup_step(session),
        "readiness": None,  # P09.9 fills this from the draft's readiness.
    }
