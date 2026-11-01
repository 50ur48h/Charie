"""Let findings share the empty label (P10.5)."""

from alembic import op
from sqlalchemy import text

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_notebook_items_message_id", "notebook_items", type_="unique")
    op.create_index(
        "uq_notebook_items_message_id_label",
        "notebook_items",
        ["message_id", "label"],
        unique=True,
        postgresql_where=text("label <> ''"),
    )


def downgrade() -> None:
    op.drop_index("uq_notebook_items_message_id_label", table_name="notebook_items")
    op.create_unique_constraint(
        "uq_notebook_items_message_id", "notebook_items", ["message_id", "label"]
    )
