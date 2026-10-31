"""Independent examiner SQL: unsafe never runs, comparison is keyed (P09.8)."""

from types import SimpleNamespace

import pytest

from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.knowledge import sql_writer
from charie.shared.knowledge.sql_writer import (
    ExaminerBlocked,
    compare_results,
    tolerance_for,
    write_checked_sql,
)
from charie.shared.safety.catalog import Catalog


def _catalog() -> Catalog:
    return Catalog(
        tables=["shop.orders"],
        forbidden_tables=[],
        required_filters=[],
        links=[],
    )


def _brief(**overrides) -> dict:
    base = {
        "question": "What were net sales in November 2025?",
        "period_start": "2025-11-01",
        "period_end": "2025-11-30",
        "splits": [],
        "scope_table": "shop.orders",
        "time_column": "orders.created_at",
        "time_zone": "America/Chicago",
        "structure": "shop.orders(order_id, total_amount, created_at).",
    }
    base.update(overrides)
    return {"input": base, "catalog": _catalog()}


def _client(fake: FakeAi) -> AiClient:
    return AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)


def _run(columns: list[str], rows: list[list], seen: list):
    def run(sql: str):
        seen.append(sql)
        return SimpleNamespace(columns=columns, rows=rows)

    return run


def test_examiner_independent(monkeypatch) -> None:
    """The AI input carries no recipe SQL and no expected answer."""
    recipe_sql = "SELECT SUM(orders.total_amount) AS total FROM shop.orders AS orders"
    fake = FakeAi().reply(
        "write_sql",
        {"sql": recipe_sql, "notes": "One query."},
    )
    monkeypatch.setattr(sql_writer, "get_ai", lambda: _client(fake))
    seen: list = []
    written = write_checked_sql(_brief(), _run(["total"], [[410]], seen), learning_run_id=None)
    assert seen == [recipe_sql]
    assert written.columns == ["total"]
    assert written.rows == [[410]]
    (job, messages) = fake.calls[0]
    assert job == "write_sql"
    shown = "\n".join(str(message) for message in messages)
    assert recipe_sql not in shown
    assert "410" not in shown


def test_checker_blocks(monkeypatch) -> None:
    """An unsafe examiner query never reaches the database."""
    fake = FakeAi().reply("write_sql", {"sql": "SELECT * FROM shop.secrets", "notes": ""})
    monkeypatch.setattr(sql_writer, "get_ai", lambda: _client(fake))
    seen: list = []
    with pytest.raises(ExaminerBlocked):
        write_checked_sql(_brief(), _run(["total"], [[1]], seen), learning_run_id=None)
    assert seen == []


def test_keyed_comparison() -> None:
    """Row order never matters; decimals keep their tolerance."""
    recipe_columns = ["restaurant_id", "total"]
    recipe_rows = [[1, 100], [2, 250]]
    examiner_rows = [[2, 250], [1, 100]]
    same = compare_results(recipe_columns, recipe_rows, recipe_columns, examiner_rows, "count")
    assert same.match is True
    assert same.tolerance == "0"
    assert (same.recipe_rows, same.examiner_rows) == (2, 2)
    off = compare_results(recipe_columns, [[1, 100]], recipe_columns, [[1, 112]], "money", "USD")
    assert off.match is False
    assert off.tolerance == "0.01"
    close = compare_results(
        recipe_columns,
        [[1, "100.005"]],
        recipe_columns,
        [[1, "100.00"]],
        "money",
        "USD",
    )
    assert close.match is True
    missing = compare_results(recipe_columns, recipe_rows, recipe_columns, [[1, 100]], "count")
    assert missing.match is False
    assert "missing" in missing.reason


def test_null_not_zero() -> None:
    """A missing value never equals zero; two missing values agree."""
    columns = ["restaurant_id", "total"]
    assert compare_results(columns, [[1, None]], columns, [[1, 0]], "count").match is False
    assert (
        "Null is not zero"
        in compare_results(columns, [[1, None]], columns, [[1, 0]], "count").reason
    )
    assert compare_results(columns, [[1, None]], columns, [[1, None]], "count").match is True
    assert str(tolerance_for("money", "JPY")) == "1"
    assert str(tolerance_for("percent")) == "0.01"
    assert str(tolerance_for("ratio")) == "0.0001"
