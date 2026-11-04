"""semantic_definitions — what a metric means here, in a form a check can read"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "charie_app"
POLICY = "org_isolation"
DEFINITIONS = "semantic_definitions"

#: A metric is something you aggregate; a dimension is something you group by.
DEFINITION_KINDS = ("metric", "dimension")

#: `proposed` until an Admin says otherwise (WP10.2d).
DEFINITION_STATUSES = ("proposed", "active", "retired")


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    op.create_table(
        DEFINITIONS,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        # The name a question is matched against — `net_revenue`.
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default=sa.text("'metric'")),
        # Prose, for the prompt. This is what makes a model use the metric correctly.
        sa.Column("description", sa.Text(), nullable=False),
        # `sum(orders.total_amount)` — how the metric is computed.
        sa.Column("expression", sa.Text(), nullable=True),
        # ...
        sa.Column(
            "required_filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # The words a person might use for it — "net revenue", "revenue net of refunds".
        sa.Column(
            "synonyms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # Where it came from, when it was not typed.
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        # The definition describes this database's columns, so it goes when the database does.
        sa.ForeignKeyConstraint(["data_source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_in_list("kind", DEFINITION_KINDS), name="kind_valid"),
        sa.CheckConstraint(_in_list("status", DEFINITION_STATUSES), name="status_valid"),
        # One meaning per name per database.
        sa.UniqueConstraint(
            "data_source_id", "name", name="uq_semantic_definitions_data_source_id_name"
        ),
    )
    op.create_index(
        "ix_semantic_definitions_org_id_data_source_id",
        DEFINITIONS,
        ["org_id", "data_source_id"],
    )

    # Revision 0002's ALTER DEFAULT PRIVILEGES already covers tables created afterwards by the...
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {DEFINITIONS} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {DEFINITIONS} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {DEFINITIONS} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {POLICY} ON {DEFINITIONS}
        USING (org_id = current_setting('app.org_id')::uuid)
        WITH CHECK (org_id = current_setting('app.org_id')::uuid)
    """)


def downgrade() -> None:
    op.drop_table(DEFINITIONS)
