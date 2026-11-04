"""agent_events accepts `knowledge_consulted` — the agent asking its documents"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
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

#: Inserted after `tool_called`, because that is what it is the result of.
TYPES_AFTER = (
    *TYPES_BEFORE[:7],
    "knowledge_consulted",
    *TYPES_BEFORE[7:],
)


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def _replace(values: Sequence[str]) -> None:
    op.drop_constraint(CONSTRAINT, EVENTS, type_="check")
    op.create_check_constraint(CONSTRAINT, EVENTS, _in_list("type", values))


def upgrade() -> None:
    _replace(TYPES_AFTER)


def downgrade() -> None:
    # Rows of the new type would violate the narrower constraint, so they go first.
    op.execute(f"DELETE FROM {EVENTS} WHERE type = 'knowledge_consulted'")
    _replace(TYPES_BEFORE)
