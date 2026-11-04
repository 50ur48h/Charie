"""conversations.archived_at — put a thread away without destroying its trace (WP11.2a)"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONVERSATIONS = "conversations"


def upgrade() -> None:
    op.add_column(
        CONVERSATIONS, sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    # The list screen's query is "mine, not archived, newest first".
    op.create_index(
        "ix_conversations_user_archived",
        CONVERSATIONS,
        ["user_id", "archived_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_user_archived", table_name=CONVERSATIONS)
    op.drop_column(CONVERSATIONS, "archived_at")
