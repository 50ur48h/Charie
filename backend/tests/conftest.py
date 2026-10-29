"""Fixtures for tests that need our Postgres.

Each run gets a fresh throwaway database (`charie_test_…`), migrated to
`head` and dropped afterwards. The working `charie` database is never
touched, and the practice database is never used here.
"""

import secrets
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from charie.shared.ai.errors import AiRealCallBlocked
from charie.shared.ai.provider import MetaProvider
from charie.shared.config import get_settings
from charie.shared.db import Base, clear_engine_cache, psycopg_url

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Methods that reach the network, patched in every unmarked test.
BLOCKED_REAL_CALLS: list = [(MetaProvider, "complete")]


@pytest.fixture(autouse=True)
def _block_real_ai_calls(request, monkeypatch):
    """Unmarked tests can't reach Meta; only `live_ai` tests can.

    A provider with a stubbed test client still runs: the stub never
    touches the network. Only a real call (no stub) raises.
    """
    if request.node.get_closest_marker("live_ai") is not None:
        return
    for cls, name in BLOCKED_REAL_CALLS:
        original = getattr(cls, name)

        def blocked(self, *args, _original=original, **kwargs):
            if getattr(self, "_client", None) is None:
                raise AiRealCallBlocked()
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(cls, name, blocked)


def alembic_config(url: str) -> Config:
    """An Alembic config for a database URL (% escaped for ConfigParser)."""
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _server_url() -> str:
    url = get_settings().database_url
    if not url:
        pytest.fail("Our Postgres isn't running. Start it with: docker compose up -d db")
    parts = urlparse(psycopg_url(url))
    return urlunparse(parts._replace(path="/postgres"))


def _make_engine(url: str):
    return create_engine(url, isolation_level="AUTOCOMMIT")


@pytest.fixture(scope="session")
def test_db_url():
    """A fresh database for the whole test run, gone afterwards."""
    try:
        server = _make_engine(_server_url())
        server.connect().close()
    except Exception:
        pytest.fail("Our Postgres isn't running. Start it with: docker compose up -d db")
    name = f"charie_test_{secrets.token_hex(4)}"
    with server.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    parts = urlparse(psycopg_url(get_settings().database_url or ""))
    url = urlunparse(parts._replace(path=f"/{name}"))
    command.upgrade(alembic_config(url), "head")
    yield url
    server.dispose()
    dropper = _make_engine(_server_url())
    with dropper.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    dropper.dispose()
    server.dispose()


@pytest.fixture()
def db(monkeypatch, test_db_url):
    """Point all code at the throwaway database, empty after each test."""
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    get_settings.cache_clear()
    clear_engine_cache()
    yield test_db_url
    engine = create_engine(test_db_url)
    names = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    engine.dispose()
    monkeypatch.undo()
    get_settings.cache_clear()
    clear_engine_cache()


@pytest.fixture()
def _test_passwords(monkeypatch, db):
    """A throwaway password and cookie secret, never the real ones."""
    monkeypatch.setenv("CHARIE_PASSWORD", "test-password")
    monkeypatch.setenv("CHARIE_SECRET_KEY", "test-secret-key-for-tests-only")
    get_settings.cache_clear()
    clear_engine_cache()
    yield
    get_settings.cache_clear()
    clear_engine_cache()


@pytest.fixture()
def chat_client(_test_passwords):
    """The chat API on the throwaway database, logged out."""
    from fastapi.testclient import TestClient

    from charie.chat.app import build_app

    with TestClient(
        build_app(), base_url="http://testserver", headers={"Origin": "http://testserver"}
    ) as client:
        yield client


@pytest.fixture()
def learner_client(_test_passwords):
    """The learner API on the throwaway database, logged out."""
    from fastapi.testclient import TestClient

    from charie.learner.app import build_app

    with TestClient(
        build_app(), base_url="http://testserver", headers={"Origin": "http://testserver"}
    ) as client:
        yield client


def log_in(client) -> None:
    """Sign the test client in with the throwaway password."""
    response = client.post("/api/login", json={"password": "test-password"})
    assert response.status_code == 200, response.text


@pytest.fixture()
def db_session(db):
    """A session on the throwaway database."""
    from sqlalchemy.orm import Session

    engine = create_engine(db)
    with Session(engine) as session:
        yield session
    engine.dispose()
