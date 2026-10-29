"""Our Postgres connection: URL forms, engine cache and sessions.

Session mechanics run against an in-memory SQLite engine, so these tests
never need our Postgres.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from charie.shared import db
from charie.shared.config import get_settings
from charie.shared.db import clear_engine_cache, get_engine, psycopg_url, session_scope


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://charie:charie@localhost:5433/charie")
    get_settings.cache_clear()
    clear_engine_cache()
    yield
    get_settings.cache_clear()
    clear_engine_cache()


def test_psycopg_url():
    assert psycopg_url("postgresql://a/b") == "postgresql+psycopg://a/b"
    assert psycopg_url("postgres://a/b") == "postgresql+psycopg://a/b"


def test_psycopg_url_leaves_other_forms_alone():
    assert psycopg_url("postgresql+psycopg://a/b") == "postgresql+psycopg://a/b"
    assert psycopg_url("sqlite:///a.db") == "sqlite:///a.db"


def test_missing_database_url_message(monkeypatch):
    from charie.shared.config import ConfigError

    def missing(name: str) -> str:
        raise ConfigError(f"{name} is missing.")

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db, "require_env", missing)
    get_settings.cache_clear()
    with pytest.raises(Exception) as raised:
        get_engine()
    assert "DATABASE_URL is missing." in str(raised.value)


def test_engine_is_cached_per_url(monkeypatch):
    first = get_engine()
    assert get_engine() is first
    monkeypatch.setenv("DATABASE_URL", "postgresql://charie:charie@localhost:5433/other")
    get_settings.cache_clear()
    assert get_engine() is not first


@pytest.fixture()
def _sqlite_engine(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, v TEXT)"))
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    return engine


def test_get_session_yields_a_session(_sqlite_engine):
    sessions = db.get_session()
    session = next(sessions)
    assert isinstance(session, Session)
    session.close()


def test_session_scope_commits(_sqlite_engine):
    with session_scope() as session:
        session.execute(text("INSERT INTO probe (v) VALUES ('a')"))
    with _sqlite_engine.connect() as conn:
        assert conn.execute(text("SELECT v FROM probe")).scalar() == "a"


def test_session_scope_rolls_back(_sqlite_engine):
    with pytest.raises(RuntimeError, match="boom"), session_scope() as session:
        session.execute(text("INSERT INTO probe (v) VALUES ('b')"))
        raise RuntimeError("boom")
    with _sqlite_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM probe")).scalar() == 0
