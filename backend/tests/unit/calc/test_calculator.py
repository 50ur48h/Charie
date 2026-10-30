"""The calculator on known tables: DuckDB, row-capped."""

import pyarrow as pa
import pytest

from charie.shared.calc.calculator import CalculatorError, calculate


def _orders() -> pa.Table:
    return pa.table(
        {
            "status": ["completed", "completed", "cancelled"],
            "total": [10.5, 20.0, 5.0],
        }
    )


def test_sums_and_groups() -> None:
    result = calculate(
        "SELECT status, SUM(total) AS revenue FROM orders GROUP BY status ORDER BY status",
        {"orders": _orders()},
    )
    assert result.columns == ["status", "revenue"]
    assert result.row_count == 2
    assert result.rows == [["cancelled", 5.0], ["completed", 30.5]]
    assert result.duration_ms >= 0


def test_empty_result() -> None:
    result = calculate("SELECT total FROM orders WHERE 1 = 0", {"orders": _orders()})
    assert result.row_count == 0
    assert result.columns == ["total"]
    assert result.rows == []


def test_unknown_table() -> None:
    with pytest.raises(CalculatorError, match="does not exist"):
        calculate("SELECT * FROM nope", {"orders": _orders()})


def test_bad_sql() -> None:
    with pytest.raises(CalculatorError):
        calculate("SELECT FROM WHERE", {"orders": _orders()})


def test_unnamed_columns_get_col_names() -> None:
    result = calculate("SELECT SUM(total), COUNT(*) FROM orders", {"orders": _orders()})
    assert result.columns == ["col_1", "col_2"]
    assert result.rows == [[35.5, 3]]


def test_row_cap() -> None:
    with pytest.raises(CalculatorError, match="over the 1 row limit"):
        calculate("SELECT total FROM orders", {"orders": _orders()}, row_limit=1)
