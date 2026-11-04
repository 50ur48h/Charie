"""users.email becomes nullable, and fabricated addresses are erased (B-009)"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FABRICATED_SUFFIX = "@unknown.invalid"


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=True)
    op.execute(f"UPDATE users SET email = NULL WHERE email LIKE '%{FABRICATED_SUFFIX}'")


def downgrade() -> None:
    # Restoring NOT NULL means restoring the fiction.
    op.execute(
        f"UPDATE users SET email = external_subject || '{FABRICATED_SUFFIX}' WHERE email IS NULL"
    )
    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
