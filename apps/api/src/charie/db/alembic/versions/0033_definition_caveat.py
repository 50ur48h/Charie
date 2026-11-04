"""semantic_definitions.caveat — what a definition makes the answer say"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "semantic_definitions",
        sa.Column("caveat", sa.Text(), nullable=True),
    )
    op.add_column(
        "semantic_definition_versions",
        sa.Column("caveat", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("semantic_definition_versions", "caveat")
    op.drop_column("semantic_definitions", "caveat")
