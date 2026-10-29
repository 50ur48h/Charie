"""Group 5: learning work and the to-do list (architecture 05, section 5)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from charie.shared.db import Base


class LearningRun(Base):
    """One learning run; it builds a draft knowledge version."""

    __tablename__ = "learning_runs"
    __table_args__ = (
        CheckConstraint("kind IN ('first', 'refresh', 'nightly')", name="kind_check"),
        CheckConstraint("status IN ('running', 'paused', 'done', 'failed')", name="status_check"),
        Index("ix_learning_runs_version_id", "version_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'running'"))
    step: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("kb_versions.id", ondelete="SET NULL")
    )
    cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), nullable=False, server_default=text("0")
    )
    summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearningEvent(Base):
    """One line of the live feed on the Learning screen."""

    __tablename__ = "learning_events"
    __table_args__ = (
        Index("ix_learning_events_run_id", "run_id"),
        Index("ix_learning_events_run_id_at", "run_id", "at"),
        CheckConstraint(
            "kind IN ('info', 'found', 'question', 'warning', 'done')", name="kind_check"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("learning_runs.id", ondelete="CASCADE"), nullable=False
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    step: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class Job(Base):
    """One item on the to-do list for the learner job."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed', 'paused', 'cancelled')",
            name="status_check",
        ),
        Index("ix_jobs_run_id", "run_id"),
        Index(
            "ix_jobs_claim",
            "priority",
            "id",
            postgresql_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("learning_runs.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
