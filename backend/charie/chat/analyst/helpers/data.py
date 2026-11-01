"""The data helper: known numbers the safe way (P10.6).

The AI never writes SQL for a known number. Code builds the query
from the recipe, checks it, runs it read-only, does the math with
DuckDB, and puts labelled numbers and tables in the notebook.
Excluded metrics never build anything (B018).
"""

import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from charie.chat.analyst.dates import ResolvedPeriod
from charie.chat.analyst.helpers.tasks import Task, _lock, task_signature
from charie.chat.analyst.notebook import (
    FindingValue,
    Notebook,
    NumberValue,
    PeriodValue,
    TableColumn,
    TableValue,
)
from charie.shared.calc.core import CalcError, ResultTable, difference, percent_change
from charie.shared.connectors.base import ConnectorError, QueryBlocked
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.crypto import decrypt_text
from charie.shared.db import session_scope
from charie.shared.knowledge.catalog import build_catalog
from charie.shared.knowledge.query_builder import (
    DateRange,
    QueryBuildError,
    QueryFilter,
    QueryRequest,
    Recipe,
    TopN,
    build_query,
    load_build_context,
)
from charie.shared.knowledge.recipe import RecipeDimension
from charie.shared.knowledge.store import list_entries
from charie.shared.knowledge.versions import usability
from charie.shared.settings import get_setting
from charie.shared.tables.chat import QueryRun
from charie.shared.tables.sources import DataSource
from charie.shared.text.numbers import (
    format_count,
    format_money,
    format_percent,
    format_ratio,
)

logger = logging.getLogger(__name__)


class _Loaded:
    """Everything one question's tasks read: recipes, sets, catalog, connector."""

    def __init__(self, session, version_id: int) -> None:
        details_by_key: dict[str, dict] = {}
        self.titles: dict[str, str] = {}
        self.dimensions: dict[str, dict] = {}
        self.names: list[dict] = []
        for entry in list_entries(session, version_id):
            details = entry.details if isinstance(entry.details, dict) else {}
            self.titles[entry.key] = entry.title or entry.key
            if entry.kind == "metric":
                details_by_key[entry.key] = details
            elif entry.kind == "dimension":
                self.dimensions[entry.key] = details
            elif entry.kind == "name":
                self.names.append(details)
        self.recipes = {key: Recipe.model_validate(item) for key, item in details_by_key.items()}
        report = usability(session, version_id)
        self.usable = set(report["usable"])
        self.excluded = {item["key"]: item["reason"] for item in report["excluded"]}
        self.usable_defaults = set(report["usable_defaults"])
        zone = get_setting(session, "time_zone") or "UTC"
        self.build_context = load_build_context(session, version_id, zone)
        self.catalog = build_catalog(session, version_id)

    def recipe_title(self, key: str) -> str:
        """The entry title, or the key when nothing was learned."""
        return self.titles.get(key, key)


def customer_connector(session) -> PostgresConnector:
    """The saved customer database's connector, read-only like P05.11."""
    row = session.scalar(select(DataSource).order_by(DataSource.id.desc()).limit(1))
    if row is None:
        raise QueryBuildError("There's no connected database yet.")
    if row.kind != "postgres":
        raise QueryBuildError("Charie can only read Postgres databases itself.")
    return PostgresConnector(
        row.host,
        row.port or 5432,
        row.database,
        row.username,
        decrypt_text(row.password_encrypted),
    )


def add_period_items(ctx) -> None:
    """Each resolved period as a `p` item, in order (P10.6 Task 2)."""
    with session_scope() as session:
        book = Notebook(session, ctx.message_id, ctx.chat_id)
        for period in ctx.periods.periods:
            book.add_period(
                period.expression.says(),
                PeriodValue(
                    start=period.start.isoformat(),
                    end=period.end.isoformat(),
                    text=period.text,
                    partial=period.partial,
                    expression=period.expression.short_text(),
                ),
            )


def drop_excluded_defaults(ctx, usable_defaults: set[str]) -> list[str]:
    """Leave excluded defaults out of the understanding; returns notes."""
    understanding = ctx.understanding
    if understanding is None:
        return []
    notes: list[str] = []
    kept: list[str] = []
    for used in understanding.defaults_used:
        word = used.removeprefix("default.")
        if word in usable_defaults:
            kept.append(used)
        else:
            notes.append(f'I left out the default meaning of "{word}": it is excluded.')
    understanding.defaults_used = kept
    return notes


def _name_entry(loaded: _Loaded, value: str) -> dict | None:
    """The name item spelling this value, or None when unknown."""
    for entry in loaded.names:
        for item in entry.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("name", "")).lower() == value.lower():
                return item
    return None


def _id_column(expression: str) -> bool:
    """True when the dimension expression names an id column, not a name."""
    column = expression.split(".")[-1].strip('"').lower()
    return column == "id" or column.endswith("_id")


def _resolve_value(loaded: _Loaded, recipe: Recipe, dimension_key: str, value: str):
    """A filter value for the dimension's expression: the id for id columns."""
    item = _name_entry(loaded, value)
    if item is None:
        return value
    expression = next(
        (item.expression for item in recipe.dimensions if item.key == dimension_key), ""
    )
    if _id_column(expression):
        return item.get("id", value)
    return item.get("name", value)


def _query_filters(task: Task, loaded: _Loaded, recipe: Recipe) -> list[QueryFilter]:
    """The task's filters, with names turned into ids for id columns."""
    return [
        QueryFilter(
            dimension=filt.dimension_key,
            op="in",
            values=[
                _resolve_value(loaded, recipe, filt.dimension_key, str(value))
                for value in filt.values
            ],
        )
        for filt in task.filters
    ]


def _filter_ids(task: Task, loaded: _Loaded, recipe: Recipe) -> list:
    """Every resolved filter value, sorted, for the proof."""
    ids = [
        _resolve_value(loaded, recipe, filt.dimension_key, str(value))
        for filt in task.filters
        for value in filt.values
    ]
    return sorted(ids, key=str)


def _task_periods(task: Task, ctx) -> list[ResolvedPeriod]:
    """The task's period labels as resolved periods, in order."""
    by_label = {period.label: period for period in ctx.periods.periods}
    missing = [label for label in task.periods if label not in by_label]
    if missing:
        raise QueryBuildError(f"There's no period {missing[0]} for this question.")
    return [by_label[label] for label in task.periods]


def _what(task: Task, loaded: _Loaded) -> str:
    """`delivered orders by outlet`: the title in lower case, plus splits."""
    title = loaded.recipe_title(task.metric_key).lower()
    if not task.split_by:
        return title
    splits = " and ".join(loaded.titles.get(key, key).lower() for key in task.split_by)
    return f"{title} by {splits}"


def _period_words(periods: list[ResolvedPeriod]) -> str:
    """`1–31 Dec 2025 and 1–30 Nov 2025`."""
    return " and ".join(period.text for period in periods)


def _describe(title: str, period: ResolvedPeriod, task: Task) -> str:
    """`Delivered orders, 1–31 Dec 2025 (Bahringer LLC)`: title, period, filters."""
    text = f"{title}, {period.text}"
    if task.filters:
        phrases = [" ".join(str(value) for value in filt.values) for filt in task.filters]
        text += f" ({'; '.join(phrases)})"
    return text


def _fact_key(
    task: Task,
    loaded: _Loaded,
    recipe: Recipe,
    period: ResolvedPeriod,
    compare: ResolvedPeriod | None,
    split: dict,
    measure: str,
) -> dict:
    """Which number this is, for answer check 9 (P10.12)."""
    return {
        "metric": task.metric_key,
        "filters": _filter_ids(task, loaded, recipe),
        "split": split,
        "period": f"{period.start.isoformat()}/{period.end.isoformat()}",
        "compare_period": (
            f"{compare.start.isoformat()}/{compare.end.isoformat()}" if compare is not None else ""
        ),
        "measure": measure,
    }


def _proof(task: Task, loaded: _Loaded, run_ids: list[int], fact: dict) -> dict:
    """Where a notebook number came from."""
    return {
        "task": task_signature(task),
        "recipe_key": task.metric_key,
        "query_run_ids": run_ids,
        "way": "recipe",
        "checks": [],
        "fact_key": fact,
    }


def _cell(value) -> object:
    """One table cell JSON-safe: decimals as text, dates as days."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _format_value(recipe: Recipe, total) -> str:
    """One number in the owner's format."""
    if recipe.unit == "money":
        return format_money(str(total), recipe.currency or "USD")
    if recipe.unit == "count":
        return format_count(str(total))
    if recipe.unit == "percent":
        return format_percent(str(total))
    return format_ratio(str(total))


def _dim_title(recipe: Recipe, key: str) -> str:
    """The recipe dimension's title, or the key."""
    for dimension in recipe.dimensions:
        if dimension.key == key:
            return dimension.title or key
    return key


def _save_run(
    session,
    message_id: int,
    task: Task,
    sql: str,
    ok: bool,
    status: str,
    row_count: int,
    duration_ms: int,
    error: str | None,
    reasons: list | None = None,
    way: str = "recipe",
) -> int:
    """One `query_runs` row; returns its id for the proof."""
    row = QueryRun(
        message_id=message_id,
        purpose=task.why,
        recipe_key=task.metric_key,
        way=way,
        sql_text=sql,
        check_report={"ok": ok, "reasons": reasons or []},
        status=status,
        row_count=row_count,
        duration_ms=duration_ms,
        error=error,
    )
    session.add(row)
    session.commit()
    return row.id


def _exclude_reason(task: Task, loaded: _Loaded) -> str | None:
    """Why this task must not run, or None when its metric is usable."""
    if task.metric_key not in loaded.recipes:
        return None
    if task.metric_key in loaded.usable:
        recipe = loaded.recipes[task.metric_key]
        if recipe.kind == "ratio":
            for side in (recipe.numerator, recipe.denominator):
                if side not in loaded.usable:
                    return f"It divides {side}, which is excluded."
        return None
    return loaded.excluded.get(task.metric_key, "It was never checked.")


def run_recipe_task(task: Task, ctx) -> None:
    """Get one task's numbers the safe way; failures become findings.

    One question's tasks share a lock so notebook labels stay unique.
    Every failure also adds a `failed` finding.
    """
    with _lock(ctx.message_id):
        _run_recipe_task(task, ctx)


def _run_recipe_task(task: Task, ctx) -> None:
    """The task body, under the question's lock, in one database session."""
    with session_scope() as session:
        book = Notebook(session, ctx.message_id, ctx.chat_id)
        loaded = _Loaded(session, ctx.kb_version_id)
        for note in drop_excluded_defaults(ctx, loaded.usable_defaults):
            ctx.log.add("note", note)
        try:
            periods = _task_periods(task, ctx)
            what, words = _what(task, loaded), _period_words(periods)
            seq = ctx.log.start("query", f"Getting {what} for {words}", task.why)
            reason = _exclude_reason(task, loaded)
            if reason is not None:
                raise QueryBuildError(
                    f'We can\'t use "{loaded.recipe_title(task.metric_key)}": {reason}'
                )
            if not periods:
                raise QueryBuildError(f"There's no period to get {what} for.")
            recipe = loaded.recipes[task.metric_key]
            results = [
                _run_period(session, ctx, task, loaded, recipe, period) for period in periods
            ]
        except (QueryBlocked, QueryBuildError, ConnectorError, CalcError) as err:
            _fail(ctx, book, task, seq, what, words, _failure_body(err))
            return
        if task.split_by:
            _save_split(ctx, book, task, loaded, periods, results, seq, what, words)
        else:
            _save_totals(ctx, book, task, loaded, periods, results, seq, what, words)


def _failure_body(err: Exception) -> str:
    """The failed line's body by cause, in the owner's words."""
    if isinstance(err, QueryBlocked):
        logger.warning("The safety check blocked a recipe query: %s", err)
        return "The safety check blocked the recipe's query. This is a bug in Charie."
    if isinstance(err, QueryBuildError):
        return str(err)
    if isinstance(err, ConnectorError) and err.code in ("query_timeout", "too_many_rows"):
        return str(err)
    if isinstance(err, ConnectorError):
        first = str(err).splitlines()[0] if str(err) else "nothing"
        return f"The database said: {first}."
    return str(err)


def _fail(ctx, book: Notebook, task: Task, seq: int, what: str, words: str, body: str) -> None:
    """A failed task: the failed line, then the finding. No numbers."""
    _ = words
    ctx.log.finish(seq, status="failed", body=body)
    book.add_finding(what, FindingValue(type="failed", text=body, task=task_signature(task)))


def _run_period(session, ctx, task: Task, loaded: _Loaded, recipe: Recipe, period: ResolvedPeriod):
    """Build, check, run and total one period; saves its `query_runs` row."""
    request = QueryRequest(
        period=DateRange(start=period.start.isoformat(), end=period.end.isoformat()),
        dimensions=list(task.split_by),
        filters=_query_filters(task, loaded, recipe),
        top_n=TopN(n=task.top_n) if task.top_n else None,
    )
    try:
        built = build_query(task.metric_key, loaded.recipes, request, loaded.build_context)
    except QueryBuildError as err:
        _save_run(session, ctx.message_id, task, "", False, "failed", 0, 0, str(err))
        raise
    connector = customer_connector(session)
    try:
        result = connector.run_checked(built.sql, loaded.catalog)
    except QueryBlocked as err:
        _save_run(
            session,
            ctx.message_id,
            task,
            built.sql,
            False,
            "blocked",
            0,
            0,
            str(err),
            reasons=list(err.reasons),
        )
        raise
    except ConnectorError as err:
        status = "timeout" if err.code == "query_timeout" else "failed"
        _save_run(session, ctx.message_id, task, built.sql, True, status, 0, 0, str(err))
        raise
    run_id = _save_run(
        session,
        ctx.message_id,
        task,
        built.sql,
        True,
        "ok",
        result.row_count,
        result.duration_ms,
        None,
    )
    table = ResultTable(result.columns, [[_cell(value) for value in row] for row in result.rows])
    return built, result, table, run_id


def _save_totals(ctx, book, task, loaded, periods, results, seq, what, words) -> None:
    """Totals without a split: a number per period, then changes."""
    recipe = loaded.recipes[task.metric_key]
    title = loaded.recipe_title(task.metric_key)
    totals: list = []
    for period, (_, result, table, run_id) in zip(periods, results, strict=True):
        total = table.total("value") if "value" in result.columns else None
        if total is None:
            book.add_finding(
                title,
                FindingValue(
                    type="nothing_found",
                    text=f"There is no {what} for {period.text}.",
                    task=task_signature(task),
                ),
            )
            totals.append(None)
            continue
        # Percent ratios arrive as points out of 100 from the builder.
        book.add_number(
            _describe(title, period, task),
            NumberValue(
                value=str(total), unit=recipe.unit, currency=recipe.currency, style="value"
            ),
            proof=_proof(
                task, loaded, [run_id], _fact_key(task, loaded, recipe, period, None, {}, "value")
            ),
        )
        totals.append(total)
    for pos in range(1, len(periods)):
        if totals[0] is None or totals[pos] is None:
            continue
        _save_change(
            book, task, loaded, recipe, title, totals[0], totals[pos], periods[0], periods[pos]
        )
    main_built, main_result, _, _ = results[0]
    ctx.log.finish(
        seq,
        status="done",
        body=f'Used the tested "{title}" recipe.',
        details={
            "sql": main_built.sql,
            "rows": main_result.row_count,
            "seconds": round(main_result.duration_ms / 1000, 1),
            "recipe": task.metric_key,
        },
    )
    if len(periods) == 2 and totals[0] is not None and totals[1] is not None:
        _found_line(book, ctx, recipe, title, totals[0], totals[1], periods[1])


def _save_change(book, task, loaded, recipe, title, new_total, old_total, main, compare) -> None:
    """One comparison's change and % change, or a note when currencies clash."""
    currency = recipe.currency or None
    try:
        change = difference(new_total, old_total, currency, currency)
        percent = percent_change(new_total, old_total, currency, currency)
    except CalcError as err:
        book.add_finding(title, FindingValue(type="note", text=str(err), task=task_signature(task)))
        return
    if change is None:
        return
    desc = f"Change in {title}, {main.text} vs {compare.text}"
    book.add_number(
        desc,
        NumberValue(value=str(change), unit=recipe.unit, currency=recipe.currency, style="change"),
        proof=_proof(
            task, loaded, [], _fact_key(task, loaded, recipe, main, compare, {}, "change")
        ),
    )
    if percent is not None:
        book.add_number(
            desc,
            NumberValue(value=str(percent), unit="percent", currency="", style="change"),
            proof=_proof(
                task,
                loaded,
                [],
                _fact_key(task, loaded, recipe, main, compare, {}, "percent_change"),
            ),
        )


def _found_line(book, ctx, recipe, title, new_total, old_total, compare) -> None:
    """`Found: Delivered orders was 191, up 13.7% on 1–30 Nov 2025.`"""
    del book
    currency = recipe.currency or None
    try:
        change = difference(new_total, old_total, currency, currency)
        percent = percent_change(new_total, old_total, currency, currency)
    except CalcError:
        return
    if change is None or percent is None:
        return
    direction = "up" if change >= 0 else "down"
    ctx.log.add(
        "found",
        f"Found: {title} was {_format_value(recipe, new_total)}, "
        f"{direction} {format_percent(str(abs(percent)))} on {compare.text}.",
    )


def _save_split(ctx, book, task, loaded, periods, results, seq, what, words) -> None:
    """A split: one table for the main period, movers with a comparison."""
    recipe = loaded.recipes[task.metric_key]
    title = loaded.recipe_title(task.metric_key)
    main_built, main_result, _, _ = results[0]
    width, spans, time_pos = _split_layout(task, recipe, main_built)
    ordered = _ordered_rows(main_result.rows, width, time_pos)
    columns = _split_columns(task, loaded, recipe, main_built, len(periods) > 1)
    table_rows = [[_cell(value) for value in row] for row in ordered]
    if len(periods) > 1:
        compare_rows = {_group_key(row, width): row[width] for row in results[1][1].rows}
        table_rows = [
            [*cells, _cell(change), _cell(percent)]
            for cells, (change, percent) in [
                (cells, _row_change(cells, compare_rows, recipe, width)) for cells in table_rows
            ]
        ]
    book.add_table(
        _describe(title, periods[0], task),
        TableValue(
            columns=columns,
            rows=table_rows,
            rows_total=main_result.row_count,
            sql=main_built.sql,
        ),
        proof=_proof(
            task,
            loaded,
            [run_id for _, _, _, run_id in results],
            _fact_key(task, loaded, recipe, periods[0], None, {}, "value"),
        ),
    )
    compare = periods[1] if len(periods) > 1 else None
    if compare is not None:
        _save_movers(
            ctx,
            book,
            task,
            loaded,
            recipe,
            title,
            ordered,
            results[1][1].rows,
            periods[0],
            compare,
            width,
            spans,
        )
    ctx.log.finish(
        seq,
        status="done",
        body=f'Used the tested "{title}" recipe.',
        details={
            "sql": main_built.sql,
            "rows": main_result.row_count,
            "seconds": round(main_result.duration_ms / 1000, 1),
            "recipe": task.metric_key,
        },
    )


def _split_layout(task: Task, recipe: Recipe, built) -> tuple[int, list, int | None]:
    """Key width, per-key spans and the time column for a split result.

    The builder emits one output column per split key plus a label
    column after keys that name one; the value column comes last.
    Each span is (key, first, label_or_None) cell positions; time_pos
    is the output position of a time dimension, if any.
    """
    spans: list[tuple[str, int, int | None]] = []
    time_pos: int | None = None
    pos = 0
    for key in task.split_by:
        dimension = next((item for item in recipe.dimensions if item.key == key), None)
        if dimension is None:
            raise QueryBuildError(f'"{recipe.title or task.metric_key}" can\'t be split by {key}.')
        label_pos = pos + 1 if dimension.label_expression else None
        if dimension.kind == "time" and time_pos is None:
            time_pos = pos
        spans.append((key, pos, label_pos))
        pos += 2 if dimension.label_expression else 1
    return pos, spans, time_pos


def _group_key(row: list, width: int) -> tuple:
    """The complete dimension key: every dimension cell, never the value."""
    return tuple(str(cell) for cell in row[:width])


def _group_display(row: list, spans: list) -> str:
    """The readable group name: the label cell when one exists."""
    parts = []
    for _key, first, label in spans:
        cell = row[label] if label is not None else row[first]
        parts.append("" if cell is None else str(cell))
    return ", ".join(parts)


def _group_ids(row: list, spans: list) -> dict:
    """Each split dimension to its own id cell, JSON-safe like the table."""
    return {key: _cell(row[first]) for key, first, _label in spans}


def _ordered_rows(raw_rows: list[list], width: int, time_pos: int | None) -> list[list]:
    """Groups in display order: oldest first for time, largest first otherwise."""
    if time_pos is not None:
        return sorted(raw_rows, key=lambda row: (str(row[time_pos]), _group_key(row, width)))
    filled = [row for row in raw_rows if row[width] is not None]
    empty = [row for row in raw_rows if row[width] is None]
    return (
        sorted(
            filled,
            key=lambda row: (difference(row[width], 0), _group_key(row, width)),
            reverse=True,
        )
        + empty
    )


def _row_change(cells: list, compare_rows: dict, recipe: Recipe, width: int):
    """One row's change and % change against the comparison period."""
    old = compare_rows.get(tuple(str(cell) for cell in cells[:width]))
    new = cells[width]
    if new is None or old is None:
        return None, None
    try:
        currency = recipe.currency or None
        change = difference(new, old, currency, currency)
        percent = percent_change(new, old, currency, currency) if change is not None else None
        return change, percent
    except CalcError:
        return None, None


def _split_columns(task, loaded, recipe, built, compared: bool) -> list[TableColumn]:
    """The table columns: splits, the value, and changes with a comparison."""
    width, spans, _time_pos = _split_layout(task, recipe, built)
    columns: list[TableColumn] = []
    for key, first, label_pos in spans:
        dimension = next(
            (item for item in recipe.dimensions if item.key == key),
            RecipeDimension(key=key, title=key, kind="attribute"),
        )
        name = built.dimension_columns[first] if first < len(built.dimension_columns) else key
        columns.append(
            TableColumn(
                key=name,
                label=dimension.title or key,
                unit="",
                currency="",
                is_time=dimension.kind == "time",
            )
        )
        if label_pos is not None:
            label_name = (
                built.dimension_columns[label_pos]
                if label_pos < len(built.dimension_columns)
                else f"{key}_label"
            )
            columns.append(
                TableColumn(
                    key=label_name,
                    label=f"{dimension.title or key} name",
                    unit="",
                    currency="",
                    is_time=False,
                )
            )
    columns.append(
        TableColumn(
            key="value",
            label=loaded.recipe_title(task.metric_key),
            unit=recipe.unit,
            currency=recipe.currency,
            is_time=False,
        )
    )
    if compared:
        columns.append(
            TableColumn(key="change", label="Change", unit=recipe.unit, currency=recipe.currency)
        )
        columns.append(
            TableColumn(key="percent_change", label="Change %", unit="percent", currency="")
        )
    return columns


def _save_movers(
    ctx, book, task, loaded, recipe, title, ordered, compare_rows, main, compare, width, spans
):
    """The biggest rises and falls, plus the grew/total counts."""
    by_group = {_group_key(row, width): row[width] for row in compare_rows}
    moves: list[tuple] = []
    for row in ordered:
        old = by_group.get(_group_key(row, width))
        new = row[width]
        if new is None or old is None:
            continue
        try:
            currency = recipe.currency or None
            change = difference(new, old, currency, currency)
        except CalcError:
            continue
        if change is not None:
            moves.append((row, change))
    if not moves:
        return
    if len(moves) <= 6:
        picked = sorted(moves, key=lambda item: item[1], reverse=True)
    else:
        rises = sorted(
            [item for item in moves if item[1] > 0], key=lambda item: item[1], reverse=True
        )[:3]
        falls = sorted([item for item in moves if item[1] < 0], key=lambda item: item[1])[:3]
        picked = rises + falls
    for row, change in picked:
        name = _group_display(row, spans)
        book.add_number(
            f"Change in {title} at {name}, {main.text} vs {compare.text}",
            NumberValue(
                value=str(change), unit=recipe.unit, currency=recipe.currency, style="change"
            ),
            proof=_proof(
                task,
                loaded,
                [],
                _fact_key(task, loaded, recipe, main, compare, _group_ids(row, spans), "change"),
            ),
        )
    grew = sum(1 for _, change in moves if change > 0)
    dim_title = _dim_title(recipe, task.split_by[0]) if task.split_by else "rows"
    for measure, count, desc, compare_period in (
        ("count_grew", grew, f"{dim_title} that grew, {main.text} vs {compare.text}", compare),
        ("count_total", len(moves), f"{dim_title} in total, {main.text}", None),
    ):
        book.add_number(
            desc,
            NumberValue(value=str(count), unit="count", currency="", style="value"),
            proof=_proof(
                task, loaded, [], _fact_key(task, loaded, recipe, main, compare_period, {}, measure)
            ),
        )
    worst = min(moves, key=lambda item: item[1])
    if worst[1] < 0:
        name = _group_display(worst[0], spans)
        ctx.log.add(
            "found",
            f"Found: {grew} of {len(moves)} grew. The biggest drop is {name}.",
        )
    else:
        best = max(moves, key=lambda item: item[1])
        name = _group_display(best[0], spans)
        ctx.log.add(
            "found",
            f"Found: {grew} of {len(moves)} grew. The biggest rise is {name}.",
        )
