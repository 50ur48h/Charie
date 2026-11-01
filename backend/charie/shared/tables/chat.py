"""Group 6: chat (architecture 05, section 6)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from charie.shared.db import Base


class Chat(Base):
    """One chat. Deleting it deletes its messages and notebook items."""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'New chat'"))
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    private: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Message(Base):
    """One question and its checked answer."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_id", "chat_id"),
        Index("ix_messages_kb_version_id", "kb_version_id"),
        CheckConstraint("role IN ('user', 'assistant')", name="role_check"),
        CheckConstraint(
            "status IN ('thinking', 'writing', 'done', 'stopped', 'failed', 'needs_choice')",
            name="status_check",
        ),
        CheckConstraint("mode IN ('thinking', 'quick')", name="mode_check"),
        CheckConstraint("feedback IN ('up', 'down')", name="feedback_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    # `text_` so the `text()` helper below still resolves.
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    answer: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'thinking'"))
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'thinking'"))
    kb_version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("kb_versions.id", ondelete="SET NULL")
    )
    data_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    steps: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    queries: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    documents: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), nullable=False, server_default=text("0")
    )
    feedback: Mapped[str | None] = mapped_column(Text)
    feedback_note: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ThinkingEvent(Base):
    """One thinking-panel line; a reopened chat shows them again."""

    __tablename__ = "thinking_events"
    __table_args__ = (
        UniqueConstraint("message_id", "seq"),
        Index("ix_thinking_events_message_id", "message_id"),
        CheckConstraint(
            "kind IN ('step', 'found', 'query', 'document', 'decision', 'check', 'note')",
            name="kind_check",
        ),
        CheckConstraint("status IN ('running', 'done', 'failed')", name="status_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'running'"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class NotebookItem(Base):
    """One saved notebook card (number, table, period, quote or finding)."""

    __tablename__ = "notebook_items"
    __table_args__ = (
        # Labels stay unique per message; findings share the empty label.
        Index(
            "uq_notebook_items_message_id_label",
            "message_id",
            "label",
            unique=True,
            postgresql_where=text("label <> ''"),
        ),
        Index("ix_notebook_items_message_id", "message_id"),
        Index("ix_notebook_items_chat_id", "chat_id"),
        CheckConstraint(
            "kind IN ('number', 'table', 'period', 'quote', 'finding')",
            name="kind_check",
        ),
        CheckConstraint("status IN ('ok', 'replaced')", name="status_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ok'"))
    replaced_by: Mapped[str | None] = mapped_column(Text)
    replace_reason: Mapped[str | None] = mapped_column(Text)
    proof: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class QueryRun(Base):
    """Every query Charie ran on the customer's database."""

    __tablename__ = "query_runs"
    __table_args__ = (
        Index("ix_query_runs_message_id", "message_id"),
        Index("ix_query_runs_learning_run_id", "learning_run_id"),
        CheckConstraint("way IN ('recipe', 'A', 'B', 'examiner')", name="way_check"),
        CheckConstraint("status IN ('ok', 'blocked', 'failed', 'timeout')", name="status_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL")
    )
    learning_run_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("learning_runs.id", ondelete="SET NULL")
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    recipe_key: Mapped[str | None] = mapped_column(Text)
    way: Mapped[str | None] = mapped_column(Text)
    sql_text: Mapped[str | None] = mapped_column(Text)
    check_report: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class Memory(Base):
    """Something to remember across chats."""

    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_source_chat_id", "source_chat_id"),
        CheckConstraint("kind IN ('meaning', 'focus', 'format', 'other')", name="kind_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # `text_` so the `text()` helper below still resolves.
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_chat_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="SET NULL")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
