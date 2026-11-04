"""agent_events accepts `model_called`; agent_runs.model records the model a person picked"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENTS = "agent_events"
CONSTRAINT = "type_valid"

#: Written out rather than imported from `charie.db.models`, for the reason revision 0013 gives.
TYPES_BEFORE = (
    "run_started",
    "intent_classified",
    "context_selected",
    "capability_checked",
    "plan_created",
    "step_started",
    "tool_called",
    "knowledge_consulted",
    "sql_validated",
    "sql_rejected",
    "query_executed",
    "result_summarized",
    "finding_added",
    "hypothesis_updated",
    "reflection",
    "critic_verdict",
    "budget_warning",
    "budget_exhausted",
    "answer_composed",
    "run_finished",
    "error",
)

TYPES_AFTER = (*TYPES_BEFORE[:8], "model_called", *TYPES_BEFORE[8:])


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def _replace(values: Sequence[str]) -> None:
    op.drop_constraint(CONSTRAINT, EVENTS, type_="check")
    op.create_check_constraint(CONSTRAINT, EVENTS, _in_list("type", values))


def upgrade() -> None:
    _replace(TYPES_AFTER)
    op.add_column("agent_runs", sa.Column("model", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "model")
    op.execute(f"DELETE FROM {EVENTS} WHERE type = 'model_called'")
    _replace(TYPES_BEFORE)
