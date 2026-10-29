"""Group 4: owner questions and the learner to-do list (05, section 4)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from charie.shared.db import Base


class OwnerQuestion(Base):
    """A question for the owner, with the answers it affects."""

    __tablename__ = "owner_questions"
    __table_args__ = (
        CheckConstraint("status IN ('waiting', 'answered', 'skipped')", name="status_check"),
        CheckConstraint(
            "source IN ('learning', 'refresh', 'nightly', 'chat')",
            name="source_check",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'waiting'"))
    rank: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    importance: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    options: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    default_option: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[dict | None] = mapped_column(JSONB)
    affects: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LearnerTodo(Base):
    """Something the learner should look at, mostly sent from the chat."""

    __tablename__ = "learner_todos"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('correction', 'unknown_word', 'new_metric', 'meaning_change')",
            name="kind_check",
        ),
        CheckConstraint("status IN ('open', 'done', 'dismissed')", name="status_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    # `text_` so the `text()` helper below still resolves.
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
