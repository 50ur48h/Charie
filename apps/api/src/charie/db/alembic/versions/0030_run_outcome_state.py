"""agent_runs.outcome_state and .unanswered — a question can be half-answered (B-134, D-044)"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

#: The three endings a run can have once it has finished.
OUTCOME_STATES = ("answered", "partly", "refused")


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("outcome_state", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("unanswered", sa.Text(), nullable=True))

    # What the row already said, and nothing beyond it.
    op.execute(
        "UPDATE agent_runs SET outcome_state = CASE "
        "WHEN answered IS TRUE THEN 'answered' "
        "WHEN answered IS FALSE THEN 'refused' "
        "END"
    )

    op.create_check_constraint(
        "outcome_state_valid",
        "agent_runs",
        "outcome_state IS NULL OR outcome_state IN ({})".format(
            ", ".join(f"'{state}'" for state in OUTCOME_STATES)
        ),
    )
    # The property the card depends on, enforced where it cannot be edited away.
    op.create_check_constraint(
        "partly_names_what_is_missing",
        "agent_runs",
        "outcome_state <> 'partly' OR (unanswered IS NOT NULL AND unanswered <> '')",
    )

    op.drop_column("agent_runs", "answered")


def downgrade() -> None:
    op.add_column("agent_runs", sa.Column("answered", sa.Boolean(), nullable=True))
    # `partly` has no true boolean.
    op.execute(
        "UPDATE agent_runs SET answered = CASE "
        "WHEN outcome_state = 'answered' THEN true "
        "WHEN outcome_state IN ('partly', 'refused') THEN false "
        "END"
    )
    op.drop_constraint("partly_names_what_is_missing", "agent_runs", type_="check")
    op.drop_constraint("outcome_state_valid", "agent_runs", type_="check")
    op.drop_column("agent_runs", "unanswered")
    op.drop_column("agent_runs", "outcome_state")
