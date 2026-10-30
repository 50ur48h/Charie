"""The database's own answer: cheap plans pass, heavy ones warn, blocked never runs."""

import json

import pytest

from charie.shared.safety.catalog import Catalog
from charie.shared.safety.check_sql_cli import load_catalog, run_check
from charie.shared.safety.list_tables import list_tables
from charie.shared.safety.sql_check import explain_plan

CATALOG = Catalog(tables=["public.check_cli"])


class _StubConnector:
    """EXPLAIN answers without a database."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.ran: list[str] = []

    def run_query(self, query: str, **kwargs):
        self.ran.append(query)

        class Result:
            rows = [[self.text]]

        return Result()


def test_cheap_plan_agrees() -> None:
    stub = _StubConnector("Seq Scan on check_cli  (cost=0.00..1.02 rows=2 width=36)")
    assert explain_plan("SELECT id FROM check_cli", CATALOG, stub) is None
    assert stub.ran == ["EXPLAIN SELECT id FROM check_cli LIMIT 50001"]


def test_heavy_plan_warns() -> None:
    stub = _StubConnector("Seq Scan on check_cli  (cost=0.00..100.00 rows=60000 width=36)")
    message = explain_plan("SELECT id FROM check_cli", CATALOG, stub)
    assert message is not None
    assert "about 60000 rows" in message and "50000 row limit" in message


def test_blocked_never_reaches_the_database() -> None:
    stub = _StubConnector("Seq Scan on check_cli  (cost=0.00..1.02 rows=2 width=36)")
    assert explain_plan("DELETE FROM check_cli", CATALOG, stub) is None
    assert stub.ran == []


def _write_catalog(tmp_path) -> str:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"tables": ["public.check_cli"]}), encoding="utf-8")
    return str(path)


@pytest.fixture()
def small_table(db):
    """Two fast rows in our own test database."""
    from sqlalchemy import create_engine, text

    admin = create_engine(db.replace("+psycopg", ""))
    with admin.begin() as conn:
        conn.execute(text("CREATE TABLE check_cli (id serial primary key, amount numeric)"))
        conn.execute(text("INSERT INTO check_cli (amount) VALUES (1), (2)"))
    yield db
    with admin.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS check_cli"))
    admin.dispose()


def test_cli_limit_used_and_real_row_count(small_table, tmp_path, capsys) -> None:
    from charie.shared.connectors.postgres import PostgresConnector
    from charie.shared.safety import check_sql_cli

    catalog = load_catalog(_write_catalog(tmp_path))
    connector = PostgresConnector.from_url(small_table)
    code = check_sql_cli.main(
        [
            "--database",
            small_table,
            "--catalog",
            _write_catalog(tmp_path),
            "--query",
            "SELECT count(*) FROM check_cli",
            "--max-rows",
            "1",
            "--explain",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out.lower()
    assert "allowed" in out
    assert "the query that would run" in out
    assert "limit 2" in out
    assert "database row estimate: 1 rows" in out
    assert "heavy_query" not in out
    assert connector is not None and catalog.tables == ["public.check_cli"]


def test_cli_heavy_records_rule_while_passing(small_table, tmp_path) -> None:
    from sqlalchemy import create_engine, text

    from charie.shared.connectors.postgres import PostgresConnector

    admin = create_engine(small_table.replace("+psycopg", ""))
    with admin.begin() as conn:
        conn.execute(text("CREATE TABLE check_big AS SELECT generate_series(1, 60000) AS id"))
        conn.execute(text("ANALYZE check_big"))
    try:
        from charie.shared.safety.catalog import Catalog as BigCatalog

        catalog = BigCatalog(tables=["public.check_big"])
        connector = PostgresConnector.from_url(small_table)
        report = run_check("SELECT id FROM check_big GROUP BY id", catalog, connector, explain=True)
        assert report.ok is True
        assert "heavy_query" in report.rules
        assert any("about 60000 rows" in reason for reason in report.reasons)
    finally:
        with admin.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS check_big"))
        admin.dispose()


def test_list_tables_names_every_table_once(small_table) -> None:
    from charie.shared.connectors.postgres import PostgresConnector

    connector = PostgresConnector.from_url(small_table)
    names = list_tables(connector)
    assert names != [] and len(names) == len(set(names))
    assert all("." in name and " " not in name for name in names)
    expected = connector.run_query(
        "SELECT schemaname || '.' || tablename FROM pg_tables "
        "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
    )
    assert sorted(names) == sorted(row[0] for row in expected.rows)


@pytest.mark.practice_db
def test_one_shot_check_on_practice_db() -> None:
    """The real check path end to end on the real practice database (read-only)."""
    from charie.shared.config import require_env
    from charie.shared.connectors.postgres import PostgresConnector

    connector = PostgresConnector.from_url(require_env("PRACTICE_DB_URL"))
    first = connector.run_query(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1 LIMIT 5"
    )
    names = [f"public.{row[0]}" for row in first.rows]
    assert names != []
    report = run_check(
        f"SELECT COUNT(*) FROM {names[0].split('.', 1)[1]}",
        Catalog(tables=names),
        connector,
        explain=True,
    )
    assert report.ok is True
    refused = run_check("DELETE FROM check_items", Catalog(tables=names), connector)
    assert refused.ok is False
    assert any("Only SELECT queries are allowed" in reason for reason in refused.reasons)
