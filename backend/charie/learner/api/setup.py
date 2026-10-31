"""`GET /api/setup`: the setup guide's state (P04.2's `SetupState`)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.learner.locks import RunActiveError
from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.settings import get_setting, set_setting
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import OwnerQuestion
from charie.shared.tables.sources import DataSource, Document, OwnerNote

setup_router = APIRouter()


class FinishBody(BaseModel):
    version_id: int | None = None


class SetupState(BaseModel):
    setup_done: bool
    step: int
    readiness: dict | None = None


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


def draft_readiness(session: Session) -> dict | None:
    """The draft version's readiness report, if the self-test wrote one."""
    from charie.shared.knowledge.versions import get_draft

    draft = get_draft(session)
    if draft is None or not isinstance(draft.readiness, dict):
        return None
    return draft.readiness


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
        "readiness": draft_readiness(session),
    }


@setup_router.post("/api/setup/finish")
def finish_setup(body: FinishBody, session: Session = Depends(get_session)) -> dict:
    """Finish setup: publish the selected draft, then mark setup done.

    The first run must be done and the self-test must have written a
    readiness report. A failed publish leaves setup unfinished."""
    from charie.shared.knowledge.versions import (
        PublishBlocked,
        PublishError,
        VersionNotFound,
        get_draft,
        publish_version,
    )

    run = first_run(session)
    if run is None or run.status != "done":
        raise ApiError(409, "finish_first_run", "Finish the first learning run first.")
    if body.version_id is not None:
        draft = session.get(KbVersion, body.version_id)
        if draft is None:
            raise ApiError(404, "not_found", "Charie couldn\u2019t find that version.")
    else:
        draft = get_draft(session)
    if draft is None:
        raise ApiError(400, "no_draft", "There\u2019s no draft version to publish.")
    if not isinstance(draft.readiness, dict):
        raise ApiError(
            409,
            "finish_not_ready",
            "The self-test hasn\u2019t written a readiness report yet.",
        )
    try:
        publish_version(session, draft.id)
    except PublishBlocked as err:
        raise ApiError(409, "big_changes", str(err)) from err
    except PublishError as err:
        raise ApiError(409, "not_draft", str(err)) from err
    except (VersionNotFound, RunActiveError) as err:
        raise ApiError(409, "busy", str(err)) from err
    set_setting(session, "setup_done", True)
    return {"setup_done": True}
