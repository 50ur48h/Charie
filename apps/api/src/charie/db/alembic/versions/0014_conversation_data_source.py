"""a conversation names the database it is about (D-022)"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "conversations"
COLUMN = "data_source_id"
FK = "fk_conversations_data_source_id"
INDEX = "ix_conversations_data_source_id"


def upgrade() -> None:
    # No column comment: this codebase documents columns on the model.
    op.add_column(TABLE, sa.Column(COLUMN, postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        FK,
        source_table=TABLE,
        referent_table="data_sources",
        local_cols=[COLUMN],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    # "Which conversations point at the source I am about to remove" is the question an operator...
    op.create_index(INDEX, TABLE, [COLUMN])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_constraint(FK, TABLE, type_="foreignkey")
    op.drop_column(TABLE, COLUMN)
