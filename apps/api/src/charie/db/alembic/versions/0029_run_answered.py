"""agent_runs.answered — a refusal stops reading as an answer (B-133)"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("answered", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "answered")
