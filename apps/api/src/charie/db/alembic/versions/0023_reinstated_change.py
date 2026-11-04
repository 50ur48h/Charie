"""a definition's history learns the word `reinstated` (B-094)"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSIONS = "semantic_definition_versions"
#: The bare name. `env.py` configures the metadata's naming convention.
CONSTRAINT = "change_valid"

BEFORE = ("created", "accepted", "updated", "retired")
AFTER = ("created", "accepted", "updated", "retired", "reinstated")


def _in_list(values: Sequence[str]) -> str:
    return "change IN ({})".format(", ".join(f"'{value}'" for value in values))


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, VERSIONS, type_="check")
    op.create_check_constraint(CONSTRAINT, VERSIONS, _in_list(AFTER))


def downgrade() -> None:
    # A row already written as `reinstated` would fail the narrower constraint.
    op.execute(f"""
        DO $$
        DECLARE offending integer;
        BEGIN
            SELECT count(*) INTO offending FROM {VERSIONS} WHERE change = 'reinstated';
            IF offending > 0 THEN
                RAISE EXCEPTION
                    'cannot downgrade: % definition version row(s) record a reinstatement, '
                    'and no earlier value describes it honestly', offending;
            END IF;
        END $$;
    """)
    op.drop_constraint(CONSTRAINT, VERSIONS, type_="check")
    op.create_check_constraint(CONSTRAINT, VERSIONS, _in_list(BEFORE))
