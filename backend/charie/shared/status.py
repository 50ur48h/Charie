"""`GET /api/status`: knowledge, data, learning, spending, waiting questions."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.ai.spending import month_spent, spending_state
from charie.shared.config import get_settings
from charie.shared.db import get_session
from charie.shared.settings import get_setting
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import OwnerQuestion
from charie.shared.tables.sources import DataSource

status_router = APIRouter()


class KnowledgeStatus(BaseModel):
    version: int | None = None
    entries: int = 0
    documents: int = 0
    published_at: str | None = None


class DataStatus(BaseModel):
    name: str
    kind: str
    status: str
    data_through: datetime | None = None


class SpendingStatus(BaseModel):
    limit_usd: float
    spent_usd: float
    remaining_usd: float
    percent_used: float
    state: str
    warn_percent: float


class LearningStatus(BaseModel):
    status: str = "none"
    step_title: str | None = None
    percent: int = 0


class StatusOut(BaseModel):
    knowledge: KnowledgeStatus
    data: DataStatus | None = None
    learning: LearningStatus | None = None
    spending: SpendingStatus | None = None
    questions_waiting: int = 0
    learner_url: str | None = None


def published_knowledge(session: Session) -> dict[str, object] | None:
    """The Knowledge card from the live published version, if any."""
    from charie.shared.knowledge.versions import get_published
    from charie.shared.tables.knowledge import KbEntry
    from charie.shared.tables.sources import Document

    published = get_published(session)
    if published is None:
        return None
    entries = session.scalar(
        select(func.count()).select_from(KbEntry).where(KbEntry.version_id == published.id)
    )
    documents = session.scalar(
        select(func.count()).select_from(Document).where(Document.status != "removed")
    )
    return {
        "version": published.number,
        "entries": entries or 0,
        "documents": documents or 0,
        "published_at": published.published_at.isoformat() if published.published_at else None,
    }


def learning_progress(session: Session) -> dict[str, object]:
    """The newest run as status, step title and percent; `none` with no run."""
    run = session.scalar(select(LearningRun).order_by(LearningRun.id.desc()).limit(1))
    if run is None:
        return {"status": "none", "step_title": None, "percent": 0}
    # The step registry lives in the learner; import it lazily so the
    # chat app only pays for it on a status call.
    from charie.learner.steps import base as steps_base

    step = steps_base.STEPS.get(run.step or "")
    title = step.title if step is not None else None
    steps = run.progress.get("steps", {}) if isinstance(run.progress, dict) else {}
    done = sum(entry.get("done", 0) for entry in steps.values())
    total = sum(entry.get("total", 0) for entry in steps.values())
    return {
        "status": run.status,
        "step_title": title,
        "percent": round(done / total * 100) if total else 0,
    }


def build_status(session: Session, now: datetime | None = None) -> dict[str, object]:
    """The status both apps share."""
    at = now or datetime.now(UTC)
    knowledge: dict[str, object] = published_knowledge(session) or {
        "version": None,
        "entries": 0,
        "documents": 0,
        "published_at": None,
    }
    source = session.scalar(select(DataSource).order_by(DataSource.id.desc()).limit(1))
    data = (
        {
            "name": source.name,
            "kind": source.kind,
            "status": source.status,
            "data_through": source.data_through,
        }
        if source is not None
        else None
    )
    limit = get_setting(session, "spend_limit_usd")
    spending = None
    if limit is not None:
        warn = get_setting(session, "spend_warn_percent")
        spent = month_spent(session, at)
        spending = {
            "limit_usd": float(limit),
            "spent_usd": float(spent),
            "remaining_usd": float(max(Decimal(0), Decimal(limit) - spent)),
            "percent_used": round(float(spent) / float(limit) * 100, 1) if float(limit) else 0.0,
            "state": spending_state(spent, limit, warn),
            "warn_percent": float(warn),
        }
    waiting = (
        session.scalar(
            select(func.count()).select_from(OwnerQuestion).where(OwnerQuestion.status == "waiting")
        )
        or 0
    )
    return {
        "knowledge": knowledge,
        "data": data,
        "learning": learning_progress(session),
        "spending": spending,
        "questions_waiting": waiting,
        "learner_url": get_settings().charie_learner_url,
    }


@status_router.get("/api/status", response_model=StatusOut)
def get_status(session: Session = Depends(get_session)) -> dict[str, object]:
    return build_status(session)
