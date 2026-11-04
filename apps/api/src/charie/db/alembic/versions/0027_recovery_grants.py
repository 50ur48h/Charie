"""org_recovery_grants — a way back when no Admin can sign in (B-017)"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GRANTS = "org_recovery_grants"
POLICY = "org_recovery_grants_isolation"
APP_ROLE = "charie_app"


def upgrade() -> None:
    op.create_table(
        GRANTS,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        # SHA-256 of the token, never the token.
        sa.Column("token_hash", sa.String(64), nullable=False),
        # What this one is for, in the Admin's own words — "kept in the ops password manager".
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Single use.
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        # The record of who armed it survives their departure, unattributed rather than erased.
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["used_by"], ["users.id"], ondelete="SET NULL"),
        # The claim looks a grant up by hash alone.
        sa.UniqueConstraint("token_hash", name="uq_org_recovery_grants_token_hash"),
    )
    op.create_index("ix_org_recovery_grants_org_id", GRANTS, ["org_id"])

    # SELECT, INSERT and UPDATE: a grant is armed, then marked used or revoked.
    op.execute(f"REVOKE ALL ON {GRANTS} FROM {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {GRANTS} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {GRANTS} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {GRANTS} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {POLICY} ON {GRANTS}
        USING (org_id = current_setting('app.org_id')::uuid)
        WITH CHECK (org_id = current_setting('app.org_id')::uuid)
    """)


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {GRANTS}")
    op.drop_index("ix_org_recovery_grants_org_id", table_name=GRANTS)
    op.drop_table(GRANTS)
