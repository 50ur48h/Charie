"""Alembic runs table changes step by step, never by hand.

The URL is `sqlalchemy.url` when set (the test helper sets it), else
`DATABASE_URL`. Revision ids are plain numbers: 0001, 0002.
"""

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from charie.shared import tables  # noqa: E402, F401
from charie.shared.config import require_env  # noqa: E402
from charie.shared.db import Base, psycopg_url  # noqa: E402

config = context.config
target_metadata = Base.metadata


def get_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return psycopg_url(require_env("DATABASE_URL"))


def run_migrations_offline() -> None:
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
