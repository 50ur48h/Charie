"""catalog_tables.embedding — a table card can finally be found by meaning"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = "catalog_tables"

#: Architecture 10.1's width and `text-embedding-3-small`'s.
EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    # Already created by revision 0016 in any database that has run it.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(TABLES, sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True))
    # Partial, over exactly the rows the backfill visits: a card with text and no vector.
    op.execute(f"""
        CREATE INDEX ix_catalog_tables_unembedded ON {TABLES} (org_id, snapshot_id)
        WHERE embedding IS NULL AND card_text IS NOT NULL
    """)
    # `catalog_tables` has carried an org_isolation policy and the application role's grants...


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_catalog_tables_unembedded")
    op.drop_column(TABLES, "embedding")
