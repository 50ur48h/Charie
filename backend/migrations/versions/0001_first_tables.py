"""First 12 tables: settings, sources, knowledge and questions.

Alembic's autogenerate doesn't create extensions, and misses the HNSW and
trigram index options, so this file is written by hand.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ENTRY_KINDS = (
    "'table', 'column', 'link', 'metric', 'dimension', 'rule', 'style',"
    " 'code', 'event', 'data_problem', 'default', 'calendar', 'how_to',"
    " 'example', 'name', 'data_range'"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_settings"),
    )
    op.create_table(
        "data_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("database", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "read_only_ok",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("data_through", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('postgres', 'mysql', 'sqlserver')", name="ck_data_sources_kind_check"
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'failed')", name="ck_data_sources_status_check"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_sources"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'new'"), nullable=False),
        sa.Column("progress", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pages", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "unreadable_pages",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("fact_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("learned_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('new', 'reading', 'learned', 'failed', 'removed')",
            name="ck_documents_status_check",
        ),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_documents_progress_check"),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )
    op.create_table(
        "document_files",
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", postgresql.BYTEA(), nullable=False),
        sa.PrimaryKeyConstraint("document_id", name="pk_document_files"),
    )
    op.create_table(
        "document_sections",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column(
            "search_text",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(note, '') || ' '"
                " || coalesce(heading_path, '') || ' ' || coalesce(text, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_sections"),
    )
    op.create_index("ix_document_sections_document_id", "document_sections", ["document_id"])
    op.create_index(
        "ix_document_sections_embedding",
        "document_sections",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_document_sections_search_text",
        "document_sections",
        ["search_text"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_sections_heading_path",
        "document_sections",
        ["heading_path"],
        postgresql_using="gin",
        postgresql_ops={"heading_path": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_document_sections_note",
        "document_sections",
        ["note"],
        postgresql_using="gin",
        postgresql_ops={"note": "gin_trgm_ops"},
    )
    op.create_table(
        "doc_facts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            sa.BigInteger(),
            sa.ForeignKey("document_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'ok'"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('definition', 'formula', 'rule', 'code', 'event', 'reported_number')",
            name="ck_doc_facts_kind_check",
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'conflicting', 'needs_checking')",
            name="ck_doc_facts_status_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_doc_facts"),
    )
    op.create_index("ix_doc_facts_document_id", "doc_facts", ["document_id"])
    op.create_index("ix_doc_facts_section_id", "doc_facts", ["section_id"])
    op.create_table(
        "owner_notes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "saved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sorted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_owner_notes"),
    )
    op.create_table(
        "kb_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("made_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "summary",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("readiness", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_kb_versions_status_check",
        ),
        sa.CheckConstraint(
            "made_by IN ('first_learning', 'refresh', 'nightly', 'owner_edit')",
            name="ck_kb_versions_made_by_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kb_versions"),
        sa.UniqueConstraint("number", name="uq_kb_versions_number"),
    )
    op.create_index(
        "uq_kb_versions_published",
        "kb_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_table(
        "kb_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "version_id",
            sa.BigInteger(),
            sa.ForeignKey("kb_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "search_text",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(meaning, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(f"kind IN ({ENTRY_KINDS})", name="ck_kb_entries_kind_check"),
        sa.CheckConstraint(
            "confidence IN ('confirmed', 'checked', 'from_document', 'guessed', 'conflicting')",
            name="ck_kb_entries_confidence_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kb_entries"),
        sa.UniqueConstraint("version_id", "key", name="uq_kb_entries_version_id"),
    )
    op.create_index("ix_kb_entries_version_id", "kb_entries", ["version_id"])
    op.create_index(
        "ix_kb_entries_embedding",
        "kb_entries",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_kb_entries_search_text",
        "kb_entries",
        ["search_text"],
        postgresql_using="gin",
    )
    op.create_table(
        "kb_changes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "version_id",
            sa.BigInteger(),
            sa.ForeignKey("kb_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("change", sa.Text(), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("is_big", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.CheckConstraint(
            "change IN ('added', 'changed', 'removed')",
            name="ck_kb_changes_change_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kb_changes"),
    )
    op.create_index("ix_kb_changes_version_id", "kb_changes", ["version_id"])
    op.create_table(
        "owner_questions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'waiting'"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("importance", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "options",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("default_option", sa.Text(), nullable=True),
        sa.Column("answer", postgresql.JSONB(), nullable=True),
        sa.Column(
            "affects",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('waiting', 'answered', 'skipped')",
            name="ck_owner_questions_status_check",
        ),
        sa.CheckConstraint(
            "source IN ('learning', 'refresh', 'nightly', 'chat')",
            name="ck_owner_questions_source_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_owner_questions"),
    )
    op.create_table(
        "learner_todos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('correction', 'unknown_word', 'new_metric', 'meaning_change')",
            name="ck_learner_todos_kind_check",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'done', 'dismissed')",
            name="ck_learner_todos_status_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learner_todos"),
    )


def downgrade() -> None:
    for table in (
        "learner_todos",
        "owner_questions",
        "kb_changes",
        "kb_entries",
        "kb_versions",
        "owner_notes",
        "doc_facts",
        "document_sections",
        "document_files",
        "documents",
        "data_sources",
        "settings",
    ):
        op.drop_table(table)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
