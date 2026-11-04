"""organizations.active_data_source_id — an Admin chooses the database once (D-045)"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("active_data_source_id", sa.Uuid(), nullable=True),
    )
    # The cycle is deliberate and Postgres is fine with it.
    op.create_foreign_key(
        "fk_organizations_active_data_source_id",
        "organizations",
        "data_sources",
        ["active_data_source_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_organizations_active_data_source_id", "organizations", type_="foreignkey"
    )
    op.drop_column("organizations", "active_data_source_id")
