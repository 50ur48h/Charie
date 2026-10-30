"""The Postgres connector against our own Postgres (never the practice DB)."""

import os
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text

from charie.shared.connectors.base import ConnectorError
from charie.shared.connectors.postgres import PostgresConnector

ROLE = "charie_ro_test"
PASSWORD = "test-readonly-password"


def _owner() -> PostgresConnector:
    parts = urlparse(os.environ["DATABASE_URL"])
    scheme = parts.scheme
    assert scheme in ("postgresql", "postgresql+psycopg", "postgres"), scheme
    return PostgresConnector(
        host=parts.hostname or "localhost",
        port=parts.port or 5432,
        database=parts.path.lstrip("/"),
        username=parts.username or "",
        password=parts.password or "",
    )


def _drop_role(conn, db_name: str) -> None:
    """Revoke everything first: a role with grants can't be dropped."""
    exists = conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": ROLE})
    if exists is None:
        return
    conn.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{ROLE}"'))
    conn.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{ROLE}"'))
    conn.execute(text(f'REVOKE CONNECT ON DATABASE "{db_name}" FROM "{ROLE}"'))
    conn.execute(text(f'DROP ROLE "{ROLE}"'))


def _db_name() -> str:
    return urlparse(os.environ["DATABASE_URL"]).path.lstrip("/")


@pytest.fixture()
def read_only(db):
    """A SELECT-only role on the throwaway database, dropped after the test."""
    engine = create_engine(db)
    with engine.begin() as conn:
        _drop_role(conn, _db_name())
        conn.execute(text(f"CREATE ROLE \"{ROLE}\" LOGIN PASSWORD '{PASSWORD}'"))
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{_db_name()}" TO "{ROLE}"'))
        conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{ROLE}"'))
        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{ROLE}"'))
    owner = _owner()
    yield PostgresConnector(owner.host, owner.port, owner.database, ROLE, PASSWORD)
    with engine.begin() as conn:
        _drop_role(conn, _db_name())
    engine.dispose()


def test_owner_login_refused(db) -> None:
    assert _owner().check_read_only() is False


def test_read_only_login_passes(read_only) -> None:
    assert read_only.check_read_only() is True


def test_time_limit(read_only) -> None:
    with pytest.raises(ConnectorError) as caught:
        read_only.run_query("SELECT pg_sleep(2)", timeout_s=1)
    assert caught.value.code == "query_timeout"


def test_too_many_rows(read_only) -> None:
    with pytest.raises(ConnectorError) as caught:
        read_only.run_query("SELECT generate_series(1, 11)", max_rows=10)
    assert caught.value.code == "too_many_rows"


def test_write_refused(read_only) -> None:
    with pytest.raises(ConnectorError) as caught:
        read_only.run_query("CREATE TABLE temp_should_not_exist (id int)")
    assert caught.value.code == "write_refused"


def test_wrong_password_is_login_failed(db) -> None:
    owner = _owner()
    bad = PostgresConnector(owner.host, owner.port, owner.database, owner.username, "wrong")
    with pytest.raises(ConnectorError) as caught:
        bad.check_read_only()
    assert caught.value.code == "login_failed"


def test_summary_counts(db) -> None:
    summary = _owner().summary()
    assert summary.tables >= 22 and summary.rows >= 0
    assert summary.server_version


def test_from_url() -> None:
    connector = PostgresConnector.from_url("postgresql://u:p@dbhost:5433/shop")
    assert (connector.host, connector.port, connector.database) == ("dbhost", 5433, "shop")
    assert (connector.username, connector.password) == ("u", "p")
