"""run_checked on our own test database as the customer (never practice)."""

import os
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text

from charie.shared.connectors.base import ConnectorError, QueryBlocked
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.safety.catalog import Catalog

ROLE = "charie_check_test"
PASSWORD = "test-check-password"


def _owner() -> PostgresConnector:
    parts = urlparse(os.environ["DATABASE_URL"])
    return PostgresConnector(
        host=parts.hostname or "localhost",
        port=parts.port or 5432,
        database=parts.path.lstrip("/"),
        username=parts.username or "",
        password=parts.password or "",
    )


def _drop_role(conn, db_name: str) -> None:
    exists = conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": ROLE})
    if exists is None:
        return
    conn.execute(text(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{ROLE}"'))
    conn.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{ROLE}"'))
    conn.execute(text(f'REVOKE CONNECT ON DATABASE "{db_name}" FROM "{ROLE}"'))
    conn.execute(text(f'DROP ROLE "{ROLE}"'))
    conn.commit()


@pytest.fixture()
def checked(db):
    """A table with rows, read through a SELECT-only login."""
    owner = _owner()
    admin = create_engine(db.replace("+psycopg", ""))
    with admin.begin() as conn:
        _drop_role(conn, owner.database)
        conn.execute(text(f"CREATE ROLE \"{ROLE}\" LOGIN PASSWORD '{PASSWORD}'"))
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{owner.database}" TO "{ROLE}"'))
        conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{ROLE}"'))
        conn.execute(text("CREATE TABLE check_items (id serial primary key, name text)"))
        conn.execute(text("INSERT INTO check_items (name) VALUES ('a'), ('b')"))
        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{ROLE}"'))
    connector = PostgresConnector(owner.host, owner.port, owner.database, ROLE, PASSWORD)
    catalog = Catalog(tables=["public.check_items"])
    yield connector, catalog
    with admin.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS check_items"))
        _drop_role(conn, owner.database)
    admin.dispose()


def test_run_checked_blocks_and_runs(checked) -> None:
    connector, catalog = checked
    with pytest.raises(QueryBlocked) as blocked:
        connector.run_checked("DELETE FROM check_items", catalog)
    assert blocked.value.code == "query_blocked"
    assert "Only SELECT queries are allowed" in str(blocked.value)
    result = connector.run_checked("SELECT id, name FROM check_items", catalog)
    assert result.row_count == 2
    assert result.columns == ["id", "name"]
    # A blocked DROP never ran: the rows are still there.
    with pytest.raises(QueryBlocked):
        connector.run_checked("DROP TABLE check_items", catalog)
    assert connector.run_query("SELECT count(*) FROM check_items").rows == [[2]]


def test_run_checked_refuses_unknown_table(checked) -> None:
    connector, catalog = checked
    with pytest.raises(QueryBlocked) as blocked:
        connector.run_checked("SELECT * FROM check_other", catalog)
    assert isinstance(blocked.value, ConnectorError)
    assert "isn't in Charie's list of known tables" in str(blocked.value)
