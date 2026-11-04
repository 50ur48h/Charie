"""usage_ledger.cached_input_tokens — the discount we have been billing at full price"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usage_ledger",
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
    )
    # Cached input is a subset of input, never an addition to it.
    op.create_check_constraint(
        "cached_within_input",
        "usage_ledger",
        "cached_input_tokens IS NULL OR "
        "(cached_input_tokens >= 0 AND cached_input_tokens <= input_tokens)",
    )


def downgrade() -> None:
    op.drop_constraint("cached_within_input", "usage_ledger", type_="check")
    op.drop_column("usage_ledger", "cached_input_tokens")
