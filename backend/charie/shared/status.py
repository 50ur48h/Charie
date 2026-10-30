"""`GET /api/status`: knowledge, data, learning, spending, waiting questions."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from charie.shared.ai.spending import month_spent, spending_state
from charie.shared.db import get_session
from charie.shared.settings import get_setting
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import OwnerQuestion
from charie.shared.tables.sources import DataSource

status_router = APIRouter()


class KnowledgeStatus(BaseModel):
    version: None = None
    entries: int = 0
    documents: int = 0
    published_at: None = None


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


class LearningStatus(BaseModel):
    runs_today: int = 0
    questions_waiting: int = 0


class StatusOut(BaseModel):
    knowledge: KnowledgeStatus
    data: DataStatus | None = None
    learning: LearningStatus | None = None
    spending: SpendingStatus | None = None
    questions_waiting: int = 0


def build_status(session: Session, now: datetime | None = None) -> dict[str, object]:
    """The status both apps share; placeholders name the phase that fills them."""
    at = now or datetime.now(UTC)
    # Knowledge counts: P09.9 or P12.1 fills these from the published version.
    knowledge: dict[str, object] = {
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
    # Runs started since midnight UTC; P09.6 fills questions_waiting.
    day_start = at.replace(hour=0, minute=0, second=0, microsecond=0)
    runs_today = (
        session.scalar(
            select(func.count()).select_from(LearningRun).where(LearningRun.started_at >= day_start)
        )
        or 0
    )
    learning: dict[str, object] = {"runs_today": runs_today, "questions_waiting": 0}
    limit = get_setting(session, "spend_limit_usd")
    spending = None
    if limit is not None:
        spent = month_spent(session, at)
        warn = get_setting(session, "spend_warn_percent")
        spending = {
            "limit_usd": float(limit),
            "spent_usd": float(spent),
            "remaining_usd": float(max(Decimal(0), Decimal(limit) - spent)),
            "percent_used": round(float(spent) / float(limit) * 100, 1) if float(limit) else 0.0,
            "state": spending_state(spent, limit, warn),
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
        "learning": learning,
        "spending": spending,
        "questions_waiting": waiting,
    }


@status_router.get("/api/status", response_model=StatusOut)
def get_status(session: Session = Depends(get_session)) -> dict[str, object]:
    return build_status(session)
