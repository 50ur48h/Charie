"""Knowledge entries accept the definition kind (P08.6)."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# The project doubles check names (ck_<table>_<given name>); keep it.
NAME = "ck_kb_entries_ck_kb_entries_kind_check"

OLD_KINDS = (
    "'table', 'column', 'link', 'metric', 'dimension', 'rule', 'style',"
    " 'code', 'event', 'data_problem', 'default', 'calendar', 'how_to',"
    " 'example', 'name', 'data_range'"
)
NEW_KINDS = (
    "'table', 'column', 'link', 'metric', 'dimension', 'definition', 'rule', 'style',"
    " 'code', 'event', 'data_problem', 'default', 'calendar', 'how_to',"
    " 'example', 'name', 'data_range'"
)


def upgrade() -> None:
    op.execute(f"ALTER TABLE kb_entries DROP CONSTRAINT {NAME}")
    op.execute(f"ALTER TABLE kb_entries ADD CONSTRAINT {NAME} CHECK (kind IN ({NEW_KINDS}))")


def downgrade() -> None:
    op.execute(f"ALTER TABLE kb_entries DROP CONSTRAINT {NAME}")
    op.execute(f"ALTER TABLE kb_entries ADD CONSTRAINT {NAME} CHECK (kind IN ({OLD_KINDS}))")
