"""Group 2: sources, documents and owner notes (architecture 05, section 2)."""

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
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from charie.shared.db import Base


class DataSource(Base):
    """The customer's database connection (password stays encrypted)."""

    __tablename__ = "data_sources"
    __table_args__ = (
        CheckConstraint("kind IN ('postgres', 'mysql', 'sqlserver')", name="kind_check"),
        CheckConstraint("status IN ('connected', 'failed')", name="status_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int | None] = mapped_column(Integer)
    database: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    read_only_ok: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    data_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class Document(Base):
    """One row per uploaded file."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'reading', 'learned', 'failed', 'removed')",
            name="status_check",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'new'"))
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pages: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    unreadable_pages: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    fact_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    learned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentFile(Base):
    """The file contents, kept apart so document lists stay fast."""

    __tablename__ = "document_files"

    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content: Mapped[bytes] = mapped_column(BYTEA, nullable=False)


class DocumentSection(Base):
    """The searchable copy of the documents (the "RAG memory")."""

    __tablename__ = "document_sections"
    __table_args__ = (
        Index("ix_document_sections_document_id", "document_id"),
        Index(
            "ix_document_sections_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_document_sections_search_text",
            "search_text",
            postgresql_using="gin",
        ),
        Index(
            "ix_document_sections_heading_path",
            "heading_path",
            postgresql_using="gin",
            postgresql_ops={"heading_path": "gin_trgm_ops"},
        ),
        Index(
            "ix_document_sections_note",
            "note",
            postgresql_using="gin",
            postgresql_ops={"note": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str | None] = mapped_column(Text)
    # `text_` so the `text()` helper below still resolves.
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    search_text: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(note, '') || ' '"
            " || coalesce(heading_path, '') || ' ' || coalesce(text, ''))",
            persisted=True,
        ),
        nullable=False,
    )


class DocFact(Base):
    """A fact found in the documents."""

    __tablename__ = "doc_facts"
    __table_args__ = (
        Index("ix_doc_facts_document_id", "document_id"),
        Index("ix_doc_facts_section_id", "section_id"),
        CheckConstraint(
            "kind IN ('definition', 'formula', 'rule', 'code', 'event', 'reported_number')",
            name="kind_check",
        ),
        CheckConstraint("status IN ('ok', 'conflicting', 'needs_checking')", name="status_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("document_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ok'"))


class OwnerNote(Base):
    """One row per save of the owner's instruction file; newest wins."""

    __tablename__ = "owner_notes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # `text_` so the `text()` helper below still resolves.
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    sorted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
