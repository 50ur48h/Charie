"""Learning runs remember who paused them."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("learning_runs", sa.Column("paused_by", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_learning_runs_paused_by_check",
        "learning_runs",
        "paused_by IN ('user', 'spending')",
    )


def downgrade() -> None:
    # The naming convention doubles the name: create rendered
    # "ck_learning_runs_" + the name above, so drop needs the doubled name.
    op.drop_constraint("ck_learning_runs_ck_learning_runs_paused_by_check", "learning_runs")
    op.drop_column("learning_runs", "paused_by")
