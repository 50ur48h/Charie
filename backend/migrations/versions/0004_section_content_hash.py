"""Sections remember the content hash they were indexed from."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_sections", sa.Column("content_hash", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_sections", "content_hash")
