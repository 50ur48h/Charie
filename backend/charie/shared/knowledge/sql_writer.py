"""Independent examiner SQL: a second way to work out a number (P09.8).

The examiner sees the question, the structure meanings, tested links and
hard rules, but never the recipe SQL and never the expected answer. Code
checks the query, runs it read-only, and compares it with the recipe's own
result by dimension ids. All math goes through `charie.shared.calc`.
"""

from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from charie.shared.ai.client import get_ai
from charie.shared.calc.core import ResultTable, difference
from charie.shared.safety.sql_check import check_sql

JOB_KIND = "write_sql"

ZERO_DECIMAL_CURRENCIES = frozenset({"JPY", "KRW", "VND", "CLP", "COP", "IDR", "HUF", "TWD"})

TOLERANCES = {"count": "0", "money": "0.01", "percent": "0.01", "ratio": "0.0001"}


class ExaminerBlocked(ValueError):
    """The examiner SQL is unsafe, so it never runs."""


@dataclass(frozen=True)
class ExamTask:
    """One practice question bound to a metric, period and splits."""

    question: str
    metric_key: str
    period_start: str
    period_end: str
    splits: tuple = ()
    unit: str = "count"
    currency: str = ""


class WriteSqlForm(BaseModel):
    """The examiner's one read-only query, in fixed form."""

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(description="One read-only SELECT answering the question.")
    notes: str = Field(default="", description="What the query reads, in plain words.")


class WrittenSql(BaseModel):
    """A checked examiner query and what it returned."""

    model_config = ConfigDict(extra="forbid")

    sql: str
    notes: str = ""
    columns: list[str] = []
    rows: list[list] = []


class Comparison(BaseModel):
    """Whether two results agree, and why not."""

    model_config = ConfigDict(extra="forbid")

    match: bool
    reason: str
    tolerance: str
    recipe_rows: int
    examiner_rows: int


def tolerance_for(unit: str, currency: str = "") -> Decimal:
    """The declared comparison tolerance: exact counts, money to the coin."""
    if unit == "money" and (currency or "").upper() in ZERO_DECIMAL_CURRENCIES:
        return Decimal(1)
    return Decimal(TOLERANCES.get(unit, "0"))


def examiner_brief(session: Session, version_id: int, task: ExamTask, time_zone: str) -> dict:
    """What the examiner may see: structure, links and rules, never recipes."""
    from charie.shared.knowledge import catalog as knowledge_catalog
    from charie.shared.knowledge.query_builder import load_build_context
    from charie.shared.knowledge.store import get_entry, list_entries

    context = load_build_context(session, version_id, time_zone)
    catalog = knowledge_catalog.build_catalog(session, version_id)
    lines = []
    for entry in list_entries(session, version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        lines.append(f"{entry.key}: {entry.meaning}")
        for column in list_entries(session, version_id, kinds=["column"]):
            info = column.details if isinstance(column.details, dict) else {}
            if info.get("table") == details.get("name") and info.get("schema") == details.get(
                "schema"
            ):
                lines.append(
                    f"  {info.get('name')} ({info.get('data_type', '')}): {column.meaning}"
                )
    for link in sorted(context.links, key=lambda item: (item.from_table, item.to_table)):
        lines.append(
            f"Each {link.from_table} row belongs to one {link.to_table} row "
            f"({link.from_table}.{link.from_column} = {link.to_table}.{link.to_column})."
        )
    for table in sorted(context.required_filters):
        for sql in context.required_filters[table]:
            lines.append(f"Always apply: {sql}.")
    recipe_entry = get_entry(session, version_id, task.metric_key)
    recipe = recipe_entry.details if recipe_entry is not None else {}
    scope_table = recipe.get("table", "") if isinstance(recipe, dict) else ""
    time_column = recipe.get("time_column", "") if isinstance(recipe, dict) else ""
    return {
        "input": {
            "question": task.question,
            "period_start": task.period_start,
            "period_end": task.period_end,
            "splits": list(task.splits),
            "scope_table": scope_table,
            "time_column": time_column,
            "time_zone": context.time_zone,
            "structure": "\n".join(lines),
        },
        "catalog": catalog,
    }


def write_checked_sql(brief: dict, run, learning_run_id: int | None = None) -> WrittenSql:
    """Ask the examiner, check the SQL, run it read-only. Unsafe never runs."""
    form = get_ai().run(
        JOB_KIND, brief["input"], WriteSqlForm, app="learner", learning_run_id=learning_run_id
    )
    sql = (form.sql or "").strip()
    if not sql:
        raise ExaminerBlocked("The examiner wrote no query.")
    report = check_sql(sql, brief["catalog"])
    if not report.ok:
        raise ExaminerBlocked(f"The examiner query is refused: {'; '.join(report.reasons)}")
    try:
        result = run(sql)
    except Exception as err:
        raise ExaminerBlocked(f"The examiner query failed to run: {err}.") from err
    columns = list(result.columns) if hasattr(result, "columns") else []
    rows = [list(row) for row in result.rows] if hasattr(result, "rows") else []
    return WrittenSql(sql=report.sql, notes=form.notes or "", columns=columns, rows=rows)


def _keyed(columns: list[str], rows: list[list], side: str) -> dict[tuple, object]:
    """Rows by leading id columns, in whatever order they came back."""
    if not columns:
        raise ValueError("A result needs columns.")
    value_at = len(columns) - 1
    found = {}
    for row in rows:
        key = tuple(row[position] for position in range(value_at))
        if key in found:
            raise ValueError(f"The {side} result repeats a row for {key!r}.")
        found[key] = row[value_at]
    return found


def compare_results(
    recipe_columns: list[str],
    recipe_rows: list[list],
    examiner_columns: list[str],
    examiner_rows: list[list],
    unit: str,
    currency: str = "",
) -> Comparison:
    """Keyed comparison: same ids, exact counts, decimals within tolerance.

    Keys are the leading columns by position: dimension ids first, the
    value last. Names may differ; the ids and numbers must not.
    """
    tolerance = tolerance_for(unit, currency)
    nope = lambda reason: Comparison(  # noqa: E731 (tiny local builder)
        match=False,
        reason=reason,
        tolerance=str(tolerance),
        recipe_rows=len(recipe_rows),
        examiner_rows=len(examiner_rows),
    )
    try:
        ResultTable(columns=list(recipe_columns), rows=[list(row) for row in recipe_rows])
        ResultTable(columns=list(examiner_columns), rows=[list(row) for row in examiner_rows])
    except Exception as err:
        return nope(f"The results don't line up: {err}.")
    if len(recipe_columns) != len(examiner_columns):
        return nope("The results have different shapes.")
    if len(recipe_columns) < 1:
        return nope("A result needs columns.")
    if len(recipe_columns) == 1 and (len(recipe_rows) != 1 or len(examiner_rows) != 1):
        return nope("A total needs exactly one row.")
    try:
        wanted = _keyed(recipe_columns, recipe_rows, "recipe")
        got = _keyed(examiner_columns, examiner_rows, "examiner")
    except (ValueError, IndexError) as err:
        return nope(f"The results don't line up: {err}.")
    for key in sorted(set(wanted) | set(got), key=repr):
        if key not in wanted:
            return nope(f"The examiner has an extra row for {key!r}.")
        if key not in got:
            return nope(f"The examiner is missing a row for {key!r}.")
        first, second = wanted[key], got[key]
        if first is None and second is None:
            continue
        if first is None or second is None:
            return nope(f"Null is not zero for {key!r}.")
        gap = difference(first, second)
        if gap is None or gap < -tolerance or gap > tolerance:
            return nope(f"The numbers disagree for {key!r}.")
    return Comparison(
        match=True,
        reason="Every row matches.",
        tolerance=str(tolerance),
        recipe_rows=len(recipe_rows),
        examiner_rows=len(examiner_rows),
    )
