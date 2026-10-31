"""The /check-sql shell output: mode line, verdict, and the query that runs."""

import json

from charie.shared.connectors.base import QueryBlocked
from charie.shared.safety import check_sql_cli
from charie.shared.safety.check_sql_cli import MODE_NO_KNOWLEDGE
from charie.shared.safety.sql_check import check_sql


class _Result:
    def __init__(self, rows):
        self.rows = rows


class _FakeOurs:
    """Our database: `kb_versions` has rows only when knowledge exists."""

    def __init__(self, knowledge: bool) -> None:
        self.knowledge = knowledge

    def run_query(self, query: str, **kwargs):
        assert "kb_versions" in query
        return _Result([[1]] if self.knowledge else [])


class _FakePractice:
    """The practice database: listed tables, a cheap plan, real checks."""

    def __init__(self, tables) -> None:
        self.tables = tables

    def run_query(self, query: str, **kwargs):
        if "information_schema" in query:
            return _Result([name.split(".", 1) for name in self.tables])
        if query.strip().upper().startswith("SELECT COUNT"):
            return _Result([[3]])
        raise AssertionError(f"unexpected query: {query}")

    def explain(self, sql: str) -> dict:
        return [{"Plan": {"Total Cost": 10}}]

    def run_checked(self, sql, catalog, max_rows=50_000, explain=None):
        report = check_sql(sql, catalog, max_rows=max_rows, explain=explain or self.explain)
        if not report.ok:
            raise QueryBlocked(report.reasons)
        return self.run_query(report.sql)


def _run(argv, ours, practice, tmp_path, capsys):
    code = check_sql_cli.run(argv, ours=ours, practice=practice)
    return code, capsys.readouterr().out


def test_allowed_output_and_exit_code(tmp_path, capsys) -> None:
    code, out = _run(
        ["SELECT id FROM orders"],
        _FakeOurs(False),
        _FakePractice(["public.orders"]),
        tmp_path,
        capsys,
    )
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == MODE_NO_KNOWLEDGE
    assert lines[1] == "Allowed."
    assert lines[2] == "The query that would run:"
    assert "SELECT" in lines[3] and "LIMIT" in lines[3]


def test_blocked_output_lists_reasons(tmp_path, capsys) -> None:
    catalog = tmp_path / "traps.json"
    catalog.write_text(
        json.dumps({"tables": ["public.orders"], "forbidden_tables": ["public.orders_old"]}),
        encoding="utf-8",
    )
    code, out = _run(
        ["SELECT id FROM orders_old", "--catalog-file", str(catalog)],
        _FakeOurs(False),
        _FakePractice(["public.orders", "public.orders_old"]),
        tmp_path,
        capsys,
    )
    assert code == 1
    lines = out.splitlines()
    assert lines[0] == MODE_NO_KNOWLEDGE
    assert lines[1] == f"Extra rules from {catalog}."
    assert lines[2] == "Blocked:"
    assert lines[3].startswith("1. ")
    assert "never to use" in lines[3]
    assert lines[4] == "The query that would run:"


def test_no_knowledge_mode_line_and_catalog(tmp_path, capsys) -> None:
    code, out = _run(
        ["SELECT id FROM second"],
        _FakeOurs(False),
        _FakePractice(["public.first", "public.second"]),
        tmp_path,
        capsys,
    )
    assert code == 0
    assert out.splitlines()[0] == MODE_NO_KNOWLEDGE


def _seed_knowledge(db_session) -> None:
    from charie.shared.knowledge import store, versions

    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    for schema, name in (("shop", "orders"), ("shop", "order_lines")):
        store.upsert_entry(
            db_session,
            version_id,
            f"table.{schema}.{name}",
            "table",
            name,
            f"A table called {name}.",
            {"schema": schema, "name": name},
            "guessed",
            [{"type": "structure", "text": "Read from the database structure"}],
            "Read from the database structure",
        )
    store.upsert_entry(
        db_session,
        version_id,
        "link.shop.order_lines.order_id~shop.orders.id",
        "link",
        "order_lines.order_id to orders.id",
        "Each row of order_lines points to one row of orders.",
        {
            "from_table": "shop.order_lines",
            "to_table": "shop.orders",
            "from_columns": ["order_id"],
            "to_columns": ["id"],
            "found_by": "foreign_key",
            "cardinality": "many_to_one",
        },
        "checked",
        [{"type": "query", "text": "Tested how many rows match"}],
        "Tested how many rows match",
    )
    db_session.commit()


def test_knowledge_exists_line(db, db_session, tmp_path, capsys) -> None:
    _seed_knowledge(db_session)
    code, out = _run(
        ["SELECT id FROM shop.orders"],
        _FakeOurs(True),
        _FakePractice(["shop.orders"]),
        tmp_path,
        capsys,
    )
    assert code == 0
    assert out.splitlines()[0] == "Mode: knowledge version 1 (draft): 2 tables, 1 links."


def test_knowledge_links_block_double_counting(db, db_session, tmp_path, capsys) -> None:
    _seed_knowledge(db_session)
    code, out = _run(
        ["SELECT SUM(o.total) FROM shop.orders o JOIN shop.order_lines l ON l.order_id = o.id"],
        _FakeOurs(True),
        _FakePractice(["shop.orders", "shop.order_lines"]),
        tmp_path,
        capsys,
    )
    assert code == 1
    assert out.splitlines()[0] == "Mode: knowledge version 1 (draft): 2 tables, 1 links."
    assert "adds up" in out


def test_catalog_file_adds_rules(tmp_path, capsys) -> None:
    catalog = tmp_path / "rules.json"
    catalog.write_text(
        json.dumps(
            {
                "tables": ["public.orders"],
                "required_filters": [
                    {
                        "table": "public.orders",
                        "sql": "orders.status = 'completed'",
                        "reason": "completed orders only",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    code, out = _run(
        ["SELECT id FROM orders", "--catalog-file", str(catalog)],
        _FakeOurs(False),
        _FakePractice(["public.orders"]),
        tmp_path,
        capsys,
    )
    assert code == 1
    assert "completed orders only" in out


def test_answer_key_style_query_allowed(tmp_path, capsys) -> None:
    code, out = _run(
        [
            "SELECT ROUND((SUM(o.total_amount))::numeric, 4) FROM public.orders o "
            "WHERE o.status = 'completed'"
        ],
        _FakeOurs(False),
        _FakePractice(["public.orders", "public.order_items"]),
        tmp_path,
        capsys,
    )
    assert code == 0
    assert "Allowed." in out
