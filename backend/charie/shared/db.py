"""Our Postgres: engine, sessions and the base all tables share.

The URL comes from `DATABASE_URL` (either `postgresql://` form works).
Engines are cached per URL, so tests can point at a throwaway database.
"""

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from charie.shared.config import get_settings, require_env


def psycopg_url(url: str) -> str:
    """Use the psycopg driver for either plain Postgres URL form."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


class Base(DeclarativeBase):
    """Every table inherits this, so keys and indexes share stable names."""

    metadata = MetaData(
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ix": "ix_%(column_0_label)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
        }
    )


_engines: dict[str, object] = {}


def get_engine():
    """One engine per URL, built from `DATABASE_URL`."""
    url = psycopg_url(require_env("DATABASE_URL"))
    if url not in _engines:
        _engines[url] = create_engine(url)
    return _engines[url]


def clear_engine_cache() -> None:
    """Forget cached engines (tests use this after changing `DATABASE_URL`)."""
    _engines.clear()


def get_session() -> Generator[Session]:
    """FastAPI dependency: one session per request."""
    maker = sessionmaker(bind=get_engine())
    with maker() as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """A session for code outside requests; commits or rolls back."""
    maker = sessionmaker(bind=get_engine())
    with maker() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def database_url() -> str | None:
    """The raw `DATABASE_URL`, or None when it is not set."""
    return get_settings().database_url
