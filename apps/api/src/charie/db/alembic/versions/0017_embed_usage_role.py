"""usage_ledger accepts the `embed` role, so embedding spends land in the ledger"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEDGER = "usage_ledger"

#: The Phase 6 vocabulary, plus `embed`.
ROLES_BEFORE = ("intake", "observe", "plan", "sql", "critic", "compose")
ROLES_AFTER = (*ROLES_BEFORE, "embed")
TIERS_BEFORE = ("small", "mid", "strong")
TIERS_AFTER = (*TIERS_BEFORE, "embed")


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def _replace(constraint: str, column: str, values: Sequence[str]) -> None:
    op.drop_constraint(constraint, LEDGER, type_="check")
    op.create_check_constraint(constraint, LEDGER, _in_list(column, values))


def upgrade() -> None:
    _replace("role_valid", "role", ROLES_AFTER)
    _replace("tier_valid", "tier", TIERS_AFTER)


def downgrade() -> None:
    # Any row this revision made possible has to go before the narrower constraint can be restored.
    op.execute(f"ALTER TABLE {LEDGER} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"DELETE FROM {LEDGER} WHERE role = 'embed' OR tier = 'embed'")
    op.execute(f"ALTER TABLE {LEDGER} FORCE ROW LEVEL SECURITY")
    _replace("role_valid", "role", ROLES_BEFORE)
    _replace("tier_valid", "tier", TIERS_BEFORE)
