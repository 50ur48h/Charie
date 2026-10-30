"""Small, safe arithmetic on Arrow tables, in memory (DuckDB)."""

import time

import duckdb
import pyarrow as pa

from charie.shared.connectors.base import QueryResult


class CalculatorError(Exception):
    """The calculation failed: bad SQL, an unknown table, or too many rows."""


def calculate(query: str, tables: dict[str, pa.Table], *, row_limit: int = 50_000) -> QueryResult:
    """Run one SELECT over the named tables; nothing else is visible.

    Unnamed result columns become `col_1`, `col_2`, ... DuckDB's own error
    is surfaced simply when the SQL is wrong.
    """
    connection = duckdb.connect()
    try:
        for name, table in tables.items():
            connection.register(name, table)
        started = time.perf_counter()
        try:
            arrow = connection.sql(query).to_arrow_table()
        except duckdb.Error as err:
            raise CalculatorError(str(err)) from err
        duration_ms = int((time.perf_counter() - started) * 1000)
    finally:
        connection.close()
    if arrow.num_rows > row_limit:
        raise CalculatorError(
            f"This answer has about {arrow.num_rows} rows, over the {row_limit} "
            "row limit. Narrow it down: add a filter or a GROUP BY."
        )
    columns = []
    for position, field in enumerate(arrow.schema, start=1):
        if not field.name or "(" in field.name:
            columns.append(f"col_{position}")
        else:
            columns.append(field.name)
    rows = [[row[name] for name in arrow.schema.names] for row in arrow.to_pylist()]
    return QueryResult(
        columns=columns, rows=rows, row_count=arrow.num_rows, duration_ms=duration_ms
    )
