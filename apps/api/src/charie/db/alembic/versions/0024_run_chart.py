"""agent_runs.chart — the picture an answer carries, or why it has none (WP11.1)"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNS = "agent_runs"


def upgrade() -> None:
    # Nullable rather than defaulted to `{}`.
    op.add_column(RUNS, sa.Column("chart", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column(RUNS, "chart")
