"""Group 3: knowledge versions and entries (architecture 05, section 3)."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from charie.shared.db import Base

ENTRY_KINDS = (
    "'table', 'column', 'link', 'metric', 'dimension', 'rule', 'style',"
    " 'code', 'event', 'data_problem', 'default', 'calendar', 'how_to',"
    " 'example', 'name', 'data_range'"
)


class KbVersion(Base):
    """One version of the knowledge base; only one is published at a time."""

    __tablename__ = "kb_versions"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="status_check"),
        CheckConstraint(
            "made_by IN ('first_learning', 'refresh', 'nightly', 'owner_edit')",
            name="made_by_check",
        ),
        Index(
            "uq_kb_versions_published",
            "status",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    made_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    readiness: Mapped[dict | None] = mapped_column(JSONB)


class KbEntry(Base):
    """One piece of knowledge in a version."""

    __tablename__ = "kb_entries"
    __table_args__ = (
        UniqueConstraint("version_id", "key"),
        Index("ix_kb_entries_version_id", "version_id"),
        Index(
            "ix_kb_entries_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_kb_entries_search_text",
            "search_text",
            postgresql_using="gin",
        ),
        CheckConstraint(f"kind IN ({ENTRY_KINDS})", name="kind_check"),
        CheckConstraint(
            "confidence IN ('confirmed', 'checked', 'from_document', 'guessed', 'conflicting')",
            name="confidence_check",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kb_versions.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    search_text: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(meaning, ''))",
            persisted=True,
        ),
        nullable=False,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class KbChange(Base):
    """What changed in a version, for "Review changes"."""

    __tablename__ = "kb_changes"
    __table_args__ = (
        Index("ix_kb_changes_version_id", "version_id"),
        CheckConstraint("change IN ('added', 'changed', 'removed')", name="change_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kb_versions.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(Text, nullable=False)
    change: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    is_big: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
