"""catalog_relationships.evidence — why an inferred join was believed (B-145)"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_relationships",
        sa.Column("evidence", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_relationships", "evidence")
