"""verified_queries — Admin-approved question→SQL pairs, as few-shot grounding"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "charie_app"
POLICY = "org_isolation"
VERIFIED = "verified_queries"

#: `active` is shown to the planner; `retired` is kept and shown to nobody.
VERIFIED_STATUSES = ("active", "retired")


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    op.create_table(
        VERIFIED,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The question in the words a person would ask it.
        sa.Column("question", sa.Text(), nullable=False),
        # The approved statement.
        sa.Column("sql", sa.Text(), nullable=False),
        # Why this shape is the right one — "join through shop_id, not name".
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        # The example names this database's tables, so it goes when the database does.
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_in_list("status", VERIFIED_STATUSES), name="status_valid"),
        # One approved answer per question per database.
        sa.UniqueConstraint(
            "data_source_id", "question", name="uq_verified_queries_data_source_id_question"
        ),
    )
    op.create_index(
        "ix_verified_queries_org_id_data_source_id", VERIFIED, ["org_id", "data_source_id"]
    )

    # Revision 0002's ALTER DEFAULT PRIVILEGES already covers tables created afterwards by the...
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {VERIFIED} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {VERIFIED} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {VERIFIED} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {POLICY} ON {VERIFIED}
        USING (org_id = current_setting('app.org_id')::uuid)
        WITH CHECK (org_id = current_setting('app.org_id')::uuid)
    """)


def downgrade() -> None:
    op.drop_table(VERIFIED)
