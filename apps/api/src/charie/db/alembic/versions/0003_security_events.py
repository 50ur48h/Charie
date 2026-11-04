"""security_events: denials that belong to no tenant"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "charie_app"


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attempted_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("route", sa.String(length=200), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "outcome IN ('denied', 'error')", name=op.f("ck_security_events_outcome_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_security_events")),
    )
    op.execute("CREATE INDEX ix_security_events_ts ON security_events (ts DESC)")
    op.create_index(
        "ix_security_events_actor_subject", "security_events", ["actor_subject"], unique=False
    )
    op.create_index(
        "ix_security_events_attempted_org_id", "security_events", ["attempted_org_id"], unique=False
    )

    # Append-only for the application, exactly like audit_log.
    op.execute(f"GRANT INSERT, SELECT ON security_events TO {APP_ROLE}")
    op.execute(f"REVOKE UPDATE, DELETE ON security_events FROM {APP_ROLE}")


def downgrade() -> None:
    op.drop_index("ix_security_events_attempted_org_id", table_name="security_events")
    op.drop_index("ix_security_events_actor_subject", table_name="security_events")
    op.drop_index("ix_security_events_ts", table_name="security_events")
    op.drop_table("security_events")
