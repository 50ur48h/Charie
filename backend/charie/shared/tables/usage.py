"""Group 7: usage — one row for every AI call (architecture 05, section 7)."""

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
from sqlalchemy.orm import Mapped, mapped_column

from charie.shared.db import Base


class AiCall(Base):
    """One AI call, with its token counts and cost for the Usage page."""

    __tablename__ = "ai_calls"
    __table_args__ = (
        Index("ix_ai_calls_at", "at"),
        Index("ix_ai_calls_message_id", "message_id"),
        Index("ix_ai_calls_learning_run_id", "learning_run_id"),
        CheckConstraint("app IN ('chat', 'learner', 'tests')", name="app_check"),
        CheckConstraint(
            "reasoning_effort IN ('minimal', 'low', 'medium', 'high', 'xhigh', 'max')",
            name="reasoning_effort_check",
        ),
        CheckConstraint("status IN ('ok', 'retried', 'failed')", name="status_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    app: Mapped[str] = mapped_column(Text, nullable=False)
    job: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning_effort: Mapped[str | None] = mapped_column(Text)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), nullable=False, server_default=text("0")
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ok'"))
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )
    learning_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("learning_runs.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
