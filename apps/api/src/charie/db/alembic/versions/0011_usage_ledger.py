"""usage_ledger: every call to a model, what it cost, and what it was for"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "charie_app"
POLICY = "org_isolation"

LEDGER = "usage_ledger"

TENANT_TABLES = (LEDGER,)

#: Architecture 4.9's roles.
ROLES = ("intake", "observe", "plan", "sql", "critic", "compose")

TIERS = ("small", "mid", "strong")

#: ok — the provider answered. error — it did not, and ``error`` says so.
STATUSES = ("ok", "error")


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    op.create_table(
        LEDGER,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        # No foreign key: `agent_runs` arrives in Phase 7.
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("tier", sa.String(10), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        # True when the counts came from our own arithmetic rather than from the provider.
        sa.Column("tokens_estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
        # Null means unpriced, not free.
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        # The second call of a parse-then-repair pair.
        sa.Column("repaired", sa.Boolean(), nullable=False, server_default=sa.false()),
        #: Sanitized before it arrives: providers raise nothing that has not been.
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_in_list("role", ROLES), name="role_valid"),
        sa.CheckConstraint(_in_list("tier", TIERS), name="tier_valid"),
        sa.CheckConstraint(_in_list("status", STATUSES), name="status_valid"),
        # A failure that does not say what failed is not a record of anything.
        sa.CheckConstraint("(status = 'error') = (error IS NOT NULL)", name="error_matches_status"),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0", name="token_counts_non_negative"
        ),
    )
    # Quotas are windows: "this organization's tokens today, this month".
    op.create_index(
        "ix_usage_ledger_org_id_created_at", LEDGER, ["org_id", sa.text("created_at DESC")]
    )
    # "What did this run cost", which the trace UI shows and the budget in Phase 8 reads back...
    op.create_index("ix_usage_ledger_org_id_run_id", LEDGER, ["org_id", "run_id"])

    for table in TENANT_TABLES:
        # Revision 0002's ALTER DEFAULT PRIVILEGES already covers tables created afterwards by...
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {POLICY} ON {table}
            USING (org_id = current_setting('app.org_id')::uuid)
            WITH CHECK (org_id = current_setting('app.org_id')::uuid)
        """)


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table}")
    op.drop_table(LEDGER)
