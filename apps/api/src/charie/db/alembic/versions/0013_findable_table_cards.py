"""rewrite existing table cards so a table is findable by its own name (B-039)"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "catalog_tables"

#: FORCE row-level security applies to the migration's own owner too.
_NO_FORCE = f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY"
_FORCE = f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY"

_QUALIFIED = "schema_name || '.' || table_name"

_TO_NEW_FORM = f"""
    UPDATE {TABLE}
    SET card_text = table_name || ' (' || {_QUALIFIED} || ')'
                    || substring(card_text from length({_QUALIFIED}) + 1)
    WHERE card_text IS NOT NULL
      AND card_text LIKE {_QUALIFIED} || ' is a %'
"""


def upgrade() -> None:
    op.execute(_NO_FORCE)
    op.execute(_TO_NEW_FORM)
    op.execute(_FORCE)


def downgrade() -> None:
    op.execute(_NO_FORCE)
    op.execute(f"""
        UPDATE {TABLE}
        SET card_text = {_QUALIFIED}
                        || substring(
                               card_text
                               from length(table_name || ' (' || {_QUALIFIED} || ')') + 1
                           )
        WHERE card_text IS NOT NULL
          AND card_text LIKE table_name || ' (' || {_QUALIFIED} || ') is a %'
    """)
    op.execute(_FORCE)
