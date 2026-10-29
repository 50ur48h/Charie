"""Last 10 tables: learning work, chat and usage."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column(
            "progress",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.BigInteger(),
            sa.ForeignKey("kb_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(12, 6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('first', 'refresh', 'nightly')",
            name="ck_learning_runs_kind_check",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'paused', 'done', 'failed')",
            name="ck_learning_runs_status_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_runs"),
    )
    op.create_index("ix_learning_runs_version_id", "learning_runs", ["version_id"])
    op.create_table(
        "learning_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("learning_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("step", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('info', 'found', 'question', 'warning', 'done')",
            name="ck_learning_events_kind_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_events"),
    )
    op.create_index("ix_learning_events_run_id", "learning_events", ["run_id"])
    op.create_index("ix_learning_events_run_id_at", "learning_events", ["run_id", "at"])
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("learning_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        sa.Column(
            "run_after",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed', 'paused', 'cancelled')",
            name="ck_jobs_status_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
    )
    op.create_index("ix_jobs_run_id", "jobs", ["run_id"])
    op.create_index(
        "ix_jobs_claim",
        "jobs",
        ["priority", "id"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_table(
        "chats",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "title",
            sa.Text(),
            server_default=sa.text("'New chat'"),
            nullable=False,
        ),
        sa.Column(
            "context",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chats"),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "chat_id",
            sa.BigInteger(),
            sa.ForeignKey("chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("answer", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'thinking'"),
            nullable=False,
        ),
        sa.Column(
            "mode",
            sa.Text(),
            server_default=sa.text("'thinking'"),
            nullable=False,
        ),
        sa.Column(
            "kb_version_id",
            sa.BigInteger(),
            sa.ForeignKey("kb_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("data_through", sa.DateTime(timezone=True), nullable=True),
        sa.Column("seconds", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("steps", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("queries", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("documents", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cost_usd",
            sa.Numeric(12, 6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("feedback_note", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role_check"),
        sa.CheckConstraint(
            "status IN ('thinking', 'writing', 'done', 'stopped', 'failed', 'needs_choice')",
            name="ck_messages_status_check",
        ),
        sa.CheckConstraint("mode IN ('thinking', 'quick')", name="ck_messages_mode_check"),
        sa.CheckConstraint("feedback IN ('up', 'down')", name="ck_messages_feedback_check"),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index("ix_messages_chat_id", "messages", ["chat_id"])
    op.create_index("ix_messages_kb_version_id", "messages", ["kb_version_id"])
    op.create_table(
        "thinking_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('step', 'found', 'query', 'document', 'decision', 'check', 'note')",
            name="ck_thinking_events_kind_check",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ck_thinking_events_status_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_thinking_events"),
        sa.UniqueConstraint("message_id", "seq", name="uq_thinking_events_message_id"),
    )
    op.create_index("ix_thinking_events_message_id", "thinking_events", ["message_id"])
    op.create_table(
        "notebook_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chat_id",
            sa.BigInteger(),
            sa.ForeignKey("chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ok'"), nullable=False),
        sa.Column("replaced_by", sa.Text(), nullable=True),
        sa.Column("replace_reason", sa.Text(), nullable=True),
        sa.Column(
            "proof",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('number', 'table', 'period', 'quote', 'finding')",
            name="ck_notebook_items_kind_check",
        ),
        sa.CheckConstraint("status IN ('ok', 'replaced')", name="ck_notebook_items_status_check"),
        sa.PrimaryKeyConstraint("id", name="pk_notebook_items"),
        sa.UniqueConstraint("message_id", "label", name="uq_notebook_items_message_id"),
    )
    op.create_index("ix_notebook_items_message_id", "notebook_items", ["message_id"])
    op.create_index("ix_notebook_items_chat_id", "notebook_items", ["chat_id"])
    op.create_table(
        "query_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "learning_run_id",
            sa.BigInteger(),
            sa.ForeignKey("learning_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("recipe_key", sa.Text(), nullable=True),
        sa.Column("way", sa.Text(), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=True),
        sa.Column(
            "check_report",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "way IN ('recipe', 'A', 'B', 'examiner')", name="ck_query_runs_way_check"
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'blocked', 'failed', 'timeout')",
            name="ck_query_runs_status_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_query_runs"),
    )
    op.create_index("ix_query_runs_message_id", "query_runs", ["message_id"])
    op.create_index("ix_query_runs_learning_run_id", "query_runs", ["learning_run_id"])
    op.create_table(
        "memories",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "source_chat_id",
            sa.BigInteger(),
            sa.ForeignKey("chats.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('meaning', 'focus', 'format', 'other')",
            name="ck_memories_kind_check",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memories"),
    )
    op.create_index("ix_memories_source_chat_id", "memories", ["source_chat_id"])
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("app", sa.Text(), nullable=False),
        sa.Column("job", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("reasoning_effort", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cached_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "completion_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "reasoning_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(12, 6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ok'"), nullable=False),
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "learning_run_id",
            sa.BigInteger(),
            sa.ForeignKey("learning_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("app IN ('chat', 'learner', 'tests')", name="ck_ai_calls_app_check"),
        sa.CheckConstraint(
            "reasoning_effort IN ('minimal', 'low', 'medium', 'high', 'xhigh', 'max')",
            name="ck_ai_calls_reasoning_effort_check",
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'retried', 'failed')", name="ck_ai_calls_status_check"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_calls"),
    )
    op.create_index("ix_ai_calls_at", "ai_calls", ["at"])
    op.create_index("ix_ai_calls_message_id", "ai_calls", ["message_id"])
    op.create_index("ix_ai_calls_learning_run_id", "ai_calls", ["learning_run_id"])


def downgrade() -> None:
    for table in (
        "ai_calls",
        "memories",
        "query_runs",
        "notebook_items",
        "thinking_events",
        "messages",
        "chats",
        "jobs",
        "learning_events",
        "learning_runs",
    ):
        op.drop_table(table)
