"""table cards: the text the agent will read, and the index it is found by"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "catalog_tables"

#: 'english' rather than 'simple': a card is prose.
CONFIGURATION = "english"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("card_text", sa.Text(), nullable=True))
    op.add_column(
        TABLE,
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        TABLE,
        # The engine's own estimate, not a count.
        sa.Column("row_estimate", sa.BigInteger(), nullable=True),
    )

    # Generated, so the text and its index cannot drift.
    op.execute(
        f"ALTER TABLE {TABLE} ADD COLUMN card_tsv tsvector "
        f"GENERATED ALWAYS AS (to_tsvector('{CONFIGURATION}', COALESCE(card_text, ''))) STORED"
    )
    op.execute(f"CREATE INDEX ix_catalog_tables_card_tsv ON {TABLE} USING GIN (card_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_catalog_tables_card_tsv")
    op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS card_tsv")
    op.drop_column(TABLE, "row_estimate")
    op.drop_column(TABLE, "flags")
    op.drop_column(TABLE, "card_text")
