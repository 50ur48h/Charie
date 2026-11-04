"""knowledge_documents and knowledge_chunks — what an organization has written down"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "charie_app"
POLICY = "org_isolation"

DOCUMENTS = "knowledge_documents"
CHUNKS = "knowledge_chunks"

#: Architecture 10.1's width, and `text-embedding-3-small`'s.
EMBEDDING_DIMENSIONS = 1536

#: md | txt | pdf for V1 (plan WP10.1).
DOCUMENT_STATUSES = ("pending", "indexed", "failed")


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    # The image is `pgvector/pgvector:pg16`.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        DOCUMENTS,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        # Where the original went.
        sa.Column("blob_path", sa.String(500), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        # Why an indexing attempt failed, in words a person can act on.
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # `SET NULL` per D-016: removing a person from a deployment must not delete the record...
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_in_list("status", DOCUMENT_STATUSES), name="status_valid"),
        # A document that failed says why, and one that did not carries no excuse.
        sa.CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)",
            name="failure_reason_matches_status",
        ),
    )
    op.create_index(
        "ix_knowledge_documents_org_id_created_at",
        DOCUMENTS,
        ["org_id", sa.text("created_at DESC")],
    )

    op.create_table(
        CHUNKS,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Position within the document, 0-based and gap-free.
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        # The heading trail this chunk sits under, outermost first.
        sa.Column(
            "headings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("token_estimate", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # Nullable on purpose — see the module docstring.
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], [f"{DOCUMENTS}.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "seq", name="uq_knowledge_chunks_document_id_seq"),
    )
    # A generated tsvector, for revision 0009's reason.
    op.execute(f"""
        ALTER TABLE {CHUNKS}
        ADD COLUMN tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
    """)
    op.create_index("ix_knowledge_chunks_org_id_document_id", CHUNKS, ["org_id", "document_id"])
    op.execute(f"CREATE INDEX ix_knowledge_chunks_tsv ON {CHUNKS} USING gin (tsv)")
    # Partial, over exactly the rows the backfill has to visit.
    op.execute(f"""
        CREATE INDEX ix_knowledge_chunks_unembedded ON {CHUNKS} (org_id, document_id)
        WHERE embedding IS NULL
    """)
    # No vector index, deliberately.
    for table in (DOCUMENTS, CHUNKS):
        # Revision 0002's ALTER DEFAULT PRIVILEGES already covers tables created afterwards by...
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {POLICY} ON {table}
            USING (org_id = current_setting('app.org_id')::uuid)
            WITH CHECK (org_id = current_setting('app.org_id')::uuid)
        """)


def downgrade() -> None:
    op.drop_table(CHUNKS)
    op.drop_table(DOCUMENTS)
    # The extension is left alone. Another table may come to use it.
