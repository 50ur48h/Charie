"""agent_runs.method — how the answer was reached, in one line (B-100)"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNS = "agent_runs"


def upgrade() -> None:
    op.add_column(RUNS, sa.Column("method", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column(RUNS, "method")
