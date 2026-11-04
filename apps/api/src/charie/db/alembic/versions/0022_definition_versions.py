"""semantic_definition_versions — every state a definition has been in (B-088)"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "charie_app"
POLICY = "org_isolation"
DEFINITIONS = "semantic_definitions"
VERSIONS = "semantic_definition_versions"

#: What put the definition into this state.
DEFINITION_CHANGES = ("created", "accepted", "updated", "retired")


def _in_list(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    # The live row's version, so a reader of `semantic_definitions` alone knows which history...
    op.add_column(
        DEFINITIONS,
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        VERSIONS,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        # What the definition said at this version, in full rather than as a diff.
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("expression", sa.Text(), nullable=True),
        sa.Column(
            "required_filters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "synonyms", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("change", sa.String(20), nullable=False),
        # Who did it. `SET NULL` rather than cascade, as everywhere else.
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        # The history goes when the definition does.
        sa.ForeignKeyConstraint(["definition_id"], [f"{DEFINITIONS}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(_in_list("change", DEFINITION_CHANGES), name="change_valid"),
        # One row per version.
        sa.UniqueConstraint(
            "definition_id", "version", name="uq_semantic_definition_versions_definition_id_version"
        ),
    )
    op.create_index(
        "ix_semantic_definition_versions_org_id_definition_id",
        VERSIONS,
        ["org_id", "definition_id"],
    )

    # SELECT and INSERT, deliberately not UPDATE or DELETE.
    op.execute(f"REVOKE ALL ON {VERSIONS} FROM {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON {VERSIONS} TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {VERSIONS} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {VERSIONS} FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY {POLICY} ON {VERSIONS}
        USING (org_id = current_setting('app.org_id')::uuid)
        WITH CHECK (org_id = current_setting('app.org_id')::uuid)
    """)


def downgrade() -> None:
    op.drop_table(VERSIONS)
    op.drop_column(DEFINITIONS, "version")
