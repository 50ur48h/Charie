"""conversations, messages, runs, events and findings — the product's own record"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "charie_app"
POLICY = "org_isolation"

CONVERSATIONS = "conversations"
MESSAGES = "messages"
RUNS = "agent_runs"
EVENTS = "agent_events"
FINDINGS = "findings"

#: Newest first: this is also the order they are dropped in.
TENANT_TABLES = (FINDINGS, EVENTS, MESSAGES, RUNS, CONVERSATIONS)

#: Architecture 10.1's status domain, unabridged.
RUN_STATUSES = (
    "queued",
    "running",
    "validating",
    "completed",
    "interrupted",
    "failed",
    "budget_exhausted",
)

#: Which of those mean the run is over.
TERMINAL_STATUSES = ("completed", "interrupted", "failed", "budget_exhausted")

MESSAGE_ROLES = ("user", "assistant")

#: Architecture 10.3's event types, verbatim and closed.
EVENT_TYPES = (
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

#: How sure the agent is of a finding, in the words architecture 10.3's own example payload uses.
CONFIDENCE_LEVELS = ("high", "medium", "low")

#: Tables whose ``run_id`` becomes a real foreign key in this revision.
RUN_REFERENCES = ("query_executions", "usage_ledger")


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def _uuid_pk() -> sa.Column[uuid.UUID]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _jsonb(name: str, default: str) -> sa.Column[dict[str, object]]:
    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(f"'{default}'::jsonb"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        CONVERSATIONS,
        _uuid_pk(),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The person whose conversation this is.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_conversations_org_id_created_at",
        CONVERSATIONS,
        ["org_id", sa.text("created_at DESC")],
    )

    op.create_table(
        RUNS,
        _uuid_pk(),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'queued'")),
        # The question as asked. Duplicated from the user's message on purpose.
        sa.Column("question", sa.Text(), nullable=False),
        # What this run is allowed to spend (arch 4.4) and where it had got to.
        _jsonb("budget", "{}"),
        _jsonb("state", "{}"),
        # A rollup for the trace UI. `usage_ledger` stays authoritative.
        _jsonb("model_usage", "{}"),
        sa.Column("cost_estimate", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        #: Sanitized before it arrives, like every other error column here.
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], [f"{CONVERSATIONS}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_in_list("status", RUN_STATUSES), name="status_valid"),
        # A run that has ended says when.
        sa.CheckConstraint(
            "(status IN ({})) = (finished_at IS NOT NULL)".format(
                ", ".join(f"'{status}'" for status in TERMINAL_STATUSES)
            ),
            name="finished_at_matches_status",
        ),
    )
    op.create_index(
        "ix_agent_runs_org_id_conversation_id_created_at",
        RUNS,
        ["org_id", "conversation_id", sa.text("created_at DESC")],
    )

    op.create_table(
        MESSAGES,
        _uuid_pk(),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Beyond architecture 10.1's column list, and required by 10.2's contract for this route.
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], [f"{CONVERSATIONS}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], [f"{RUNS}.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_in_list("role", MESSAGE_ROLES), name="role_valid"),
    )
    op.create_index(
        "ix_messages_org_id_conversation_id_created_at",
        MESSAGES,
        ["org_id", "conversation_id", "created_at"],
    )
    # What makes a retried POST cheap instead of a second billed run.
    op.create_index(
        "uq_messages_idempotency_key",
        MESSAGES,
        ["org_id", "conversation_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        EVENTS,
        # bigserial per architecture 10.1: this table grows faster than any other in the product.
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        # 1-based and gap-free within a run.
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        # Built for eyes (arch 10.3): short public strings from structured tool output.
        _jsonb("payload", "{}"),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], [f"{RUNS}.id"], ondelete="CASCADE"),
        sa.CheckConstraint(_in_list("type", EVENT_TYPES), name="type_valid"),
        sa.CheckConstraint("seq > 0", name="seq_positive"),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_events_run_id_seq"),
    )
    # The only read this table has: "give me this run's events after seq N".
    op.create_index("ix_agent_events_org_id_run_id_seq", EVENTS, ["org_id", "run_id", "seq"])

    op.create_table(
        FINDINGS,
        _uuid_pk(),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        # Which executions back this up.
        sa.Column(
            "support",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("confidence", sa.String(10), nullable=False, server_default=sa.text("'medium'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], [f"{RUNS}.id"], ondelete="CASCADE"),
        sa.CheckConstraint(_in_list("confidence", CONFIDENCE_LEVELS), name="confidence_valid"),
    )
    op.create_index("ix_findings_org_id_run_id", FINDINGS, ["org_id", "run_id"])

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

    # Append-only, enforced by the database rather than by discipline.
    op.execute(f"REVOKE UPDATE, DELETE ON {EVENTS} FROM {APP_ROLE}")

    _attach_run_foreign_keys()


def _attach_run_foreign_keys() -> None:
    """Give the two ``run_id`` columns written before this table existed a key."""
    for table in RUN_REFERENCES:
        # FORCE applies row-level security to the owner as well.
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            UPDATE {table} SET run_id = NULL
            WHERE run_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM {RUNS} WHERE {RUNS}.id = {table}.run_id)
        """)
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.create_foreign_key(
            f"fk_{table}_run_id_{RUNS}",
            table,
            RUNS,
            ["run_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table in RUN_REFERENCES:
        op.drop_constraint(f"fk_{table}_run_id_{RUNS}", table, type_="foreignkey")

    op.execute(f"GRANT UPDATE, DELETE ON {EVENTS} TO {APP_ROLE}")
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table}")
        op.drop_table(table)
