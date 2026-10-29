"""The Sources database addresses on the real API (learner app only)."""

import os
from urllib.parse import urlparse

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

from charie.learner.api.sources import display_name
from charie.shared.config import get_settings
from charie.shared.crypto import decrypt_text
from charie.shared.tables.sources import DataSource
from tests.conftest import log_in

ROLE = "charie_src_test"
PASSWORD = "test-source-password"


def _parts():
    parts = urlparse(os.environ["DATABASE_URL"])
    return {
        "host": parts.hostname or "localhost",
        "port": parts.port or 5432,
        "database": parts.path.lstrip("/"),
        "username": parts.username or "",
        "password": parts.password or "",
    }


@pytest.fixture()
def enc_key(monkeypatch, db):
    """A fresh encryption key, never the real one."""
    monkeypatch.setenv("CHARIE_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def ro_role(db):
    """A SELECT-only role on the throwaway database, dropped after the test."""
    engine = create_engine(db)
    name = urlparse(db).path.lstrip("/")
    with engine.begin() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :n"), {"n": ROLE})
        if exists is not None:
            conn.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{ROLE}"'))
            conn.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{ROLE}"'))
            conn.execute(text(f'REVOKE CONNECT ON DATABASE "{name}" FROM "{ROLE}"'))
            conn.execute(text(f'DROP ROLE "{ROLE}"'))
        conn.execute(text(f"CREATE ROLE \"{ROLE}\" LOGIN PASSWORD '{PASSWORD}'"))
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO "{ROLE}"'))
        conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{ROLE}"'))
        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{ROLE}"'))
    owner = _parts()
    yield {**owner, "username": ROLE, "password": PASSWORD}
    with engine.begin() as conn:
        conn.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{ROLE}"'))
        conn.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{ROLE}"'))
        conn.execute(text(f'REVOKE CONNECT ON DATABASE "{name}" FROM "{ROLE}"'))
        conn.execute(text(f'DROP ROLE "{ROLE}"'))
    engine.dispose()


def _put(client, body):
    return client.put("/api/sources/database", json=body)


def test_get_is_null_when_nothing_saved(enc_key, learner_client) -> None:
    log_in(learner_client)
    response = learner_client.get("/api/sources/database")
    assert response.status_code == 200
    assert response.json() is None


def test_put_returns_source_without_password(enc_key, ro_role, learner_client) -> None:
    log_in(learner_client)
    body = {"kind": "postgres", **ro_role}
    response = _put(learner_client, body)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert "password" not in saved and "password_encrypted" not in saved
    assert saved["name"].endswith(" database") and "_" not in saved["name"]
    assert saved["status"] == "connected" and saved["read_only_ok"] is True
    assert saved["data_through"] is None and saved["checked_at"] is not None
    assert saved["details"]["tables"] >= 22
    again = learner_client.get("/api/sources/database").json()
    assert again is not None and again["name"] == saved["name"]


def test_name_rule() -> None:
    assert display_name("bella_forno") == "Bella Forno database"


def test_password_encrypted_in_table(enc_key, ro_role, learner_client, db_session) -> None:
    log_in(learner_client)
    assert _put(learner_client, {"kind": "postgres", **ro_role}).status_code == 200
    row = db_session.query(DataSource).one()
    assert row.password_encrypted != PASSWORD
    assert decrypt_text(row.password_encrypted) == PASSWORD


def test_owner_login_not_saved(enc_key, learner_client) -> None:
    log_in(learner_client)
    owner = _parts()
    response = _put(learner_client, {"kind": "postgres", **owner})
    assert response.status_code == 400
    assert response.json() == {
        "error": "not_read_only",
        "message": "This login can change data. Please use a read-only login.",
    }
    assert learner_client.get("/api/sources/database").json() is None


def test_test_address_saves_nothing(enc_key, ro_role, learner_client) -> None:
    log_in(learner_client)
    response = learner_client.post(
        "/api/sources/database/test", json={"kind": "postgres", **ro_role}
    )
    assert response.status_code == 200, response.text
    tested = response.json()
    assert tested["read_only_ok"] is True and tested["data_through"] is None
    assert tested["details"]["tables"] >= 22
    assert learner_client.get("/api/sources/database").json() is None


def test_empty_password_keeps_saved_one(enc_key, ro_role, learner_client, db_session) -> None:
    log_in(learner_client)
    assert _put(learner_client, {"kind": "postgres", **ro_role}).status_code == 200
    first = db_session.query(DataSource).one().password_encrypted
    kept = dict(ro_role, password="")
    assert _put(learner_client, {"kind": "postgres", **kept}).status_code == 200
    db_session.expire_all()
    assert db_session.query(DataSource).one().password_encrypted == first


def test_bad_port(enc_key, learner_client) -> None:
    log_in(learner_client)
    body = {
        "kind": "postgres",
        "host": "localhost",
        "port": 99999,
        "database": "x",
        "username": "y",
        "password": "z",
    }
    response = _put(learner_client, body)
    assert response.status_code == 400
    assert response.json()["error"] == "bad_request"
