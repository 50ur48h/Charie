"""Step 2: study the database structure, with row counts and dates (P07.6).

Fixed `pg_catalog` queries, read-only through the connector with a
60-second cap. Writes `table`, `column` and `data_range` entries, and
saves how far the data goes on the source row. Every query is saved in
`query_runs` with the run id and a plain purpose.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from charie.learner.sql import quote_ident, quote_literal, table_ref
from charie.learner.steps.base import Step, StepContext, register_step, register_step_handler
from charie.shared.connectors.base import ConnectorError
from charie.shared.knowledge import store
from charie.shared.knowledge.catalog import forbidden_tables
from charie.shared.knowledge.keys import column_key, data_range_key, table_key
from charie.shared.settings import get_setting
from charie.shared.tables.chat import QueryRun

JOB_KIND = "scan_structure"

REASON_SCANNED = "Read from the database structure"
REASON_GONE = "No longer in the database"

SOURCE_STRUCTURE = {"type": "structure", "text": "Read from the database structure"}

_OBJECT_FILTER = (
    "n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')"
    " AND c.relkind IN ('r', 'p', 'v', 'm')"
    " AND NOT c.relispartition"
    " AND has_table_privilege(c.oid, 'SELECT')"
)

_DATE_TYPES = (
    "date",
    "timestamp without time zone",
    "timestamp with time zone",
)

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


@dataclass
class _Column:
    """One column of a scanned table, with its keys filled in later."""

    schema: str
    table: str
    name: str
    position: int
    data_type: str
    nullable: bool
    comment: str
    is_primary_key: bool = False
    is_unique: bool = False


@dataclass
class _Table:
    """One table or view, with its row estimate and columns."""

    schema: str
    name: str
    is_view: bool
    comment: str
    reltuples: float
    columns: list[_Column]
    primary_key: list[str]
    foreign_keys: list[dict]


def _run_query(ctx: StepContext, purpose: str, sql: str):
    """One scan query: saved in `query_runs`, then returned (or raised)."""
    try:
        result = ctx.connector.run_query(sql)
    except ConnectorError as err:
        ctx.session.add(
            QueryRun(
                learning_run_id=ctx.run_id,
                purpose=purpose,
                sql_text=sql,
                status="timeout" if err.code == "query_timeout" else "failed",
                row_count=0,
                duration_ms=0,
                error=err.message,
            )
        )
        ctx.session.flush()
        raise
    ctx.session.add(
        QueryRun(
            learning_run_id=ctx.run_id,
            purpose=purpose,
            sql_text=sql,
            status="ok",
            row_count=result.row_count,
            duration_ms=result.duration_ms,
        )
    )
    ctx.session.flush()
    return result


def _objects(ctx: StepContext) -> list[_Table]:
    """Every table, view and column the login may read, with keys."""
    result = _run_query(
        ctx,
        "Read the list of tables",
        "SELECT n.nspname AS schema, c.relname AS name, c.relkind AS kind,"
        " c.reltuples AS rows, obj_description(c.oid) AS comment"
        " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        f" WHERE {_OBJECT_FILTER} ORDER BY 1, 2",
    )
    tables = [
        _Table(
            schema=row[0],
            name=row[1],
            is_view=row[2] in ("v", "m"),
            comment=row[4] or "",
            reltuples=row[3],
            columns=[],
            primary_key=[],
            foreign_keys=[],
        )
        for row in result.rows
    ]
    columns = _run_query(
        ctx,
        "Read the columns of every table",
        "SELECT n.nspname AS schema, c.relname AS table,"
        " a.attname AS name, a.attnum AS position,"
        " pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,"
        " NOT a.attnotnull AS nullable,"
        " col_description(c.oid, a.attnum) AS comment"
        " FROM pg_attribute a"
        " JOIN pg_class c ON c.oid = a.attrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        f" WHERE {_OBJECT_FILTER} AND a.attnum > 0 AND NOT a.attisdropped"
        " ORDER BY 1, 2, 4",
    )
    by_table: dict[tuple[str, str], _Table] = {
        (table.schema, table.name): table for table in tables
    }
    for row in columns.rows:
        table = by_table.get((row[0], row[1]))
        if table is None:
            continue
        table.columns.append(
            _Column(
                schema=row[0],
                table=row[1],
                name=row[2],
                position=row[3],
                data_type=row[4],
                nullable=bool(row[5]),
                comment=row[6] or "",
            )
        )
    keys = _run_query(
        ctx,
        "Read the primary, unique and foreign keys",
        "SELECT n.nspname AS schema, c.relname AS table, con.contype AS kind,"
        " con.conkey AS columns, fn.nspname AS ref_schema,"
        " fc.relname AS ref_table, con.confkey AS ref_columns"
        " FROM pg_constraint con"
        " JOIN pg_class c ON c.oid = con.conrelid"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " LEFT JOIN pg_class fc ON fc.oid = con.confrelid"
        " LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace"
        f" WHERE {_OBJECT_FILTER} AND c.relkind IN ('r', 'p')"
        " AND con.contype IN ('p', 'u', 'f')",
    )
    for row in keys.rows:
        table = by_table.get((row[0], row[1]))
        if table is None:
            continue
        names = [column.name for column in table.columns]
        if row[2] == "p":
            table.primary_key = [
                names[number - 1] for number in (row[3] or []) if 0 < number <= len(names)
            ]
            for column in table.columns:
                if column.name in table.primary_key:
                    column.is_primary_key = True
        elif row[2] == "u":
            unique = [names[number - 1] for number in (row[3] or []) if 0 < number <= len(names)]
            if len(unique) == 1:
                for column in table.columns:
                    if column.name == unique[0]:
                        column.is_unique = True
        else:
            from_names = [
                names[number - 1] for number in (row[3] or []) if 0 < number <= len(names)
            ]
            table.foreign_keys.append(
                {
                    "columns": from_names,
                    "ref_table": f"{row[4]}.{row[5]}",
                    "ref_numbers": list(row[6] or []),
                    "ref_columns": [],
                }
            )
    return [_resolve_ref_columns(table, by_table) for table in tables]


def _resolve_ref_columns(table: _Table, by_table: dict[tuple[str, str], _Table]) -> _Table:
    """Foreign-key attnums become names, using the other table's columns."""
    for key in table.foreign_keys:
        schema, _, name = key["ref_table"].partition(".")
        other = by_table.get((schema, name))
        names = [column.name for column in other.columns] if other is not None else []
        key["ref_columns"] = [
            names[number - 1] for number in key.pop("ref_numbers") if 0 < number <= len(names)
        ]
    return table


def _display(schema: str, name: str, taken: set[str]) -> str:
    """`orders`, or `shop.orders` when another schema has the same name."""
    return f"{schema}.{name}" if name in taken else name


def _rough(rows: float | None) -> str:
    """`about 400K rows`, `3 rows`, or `an unknown number of rows`."""
    if rows is None:
        return "an unknown number of rows"
    count = int(rows)
    if count >= 1_000_000:
        text = f"{count / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"about {text}M rows"
    if count >= 1000:
        return f"about {round(count / 1000)}K rows"
    return f"{count} row" if count == 1 else f"{count} rows"


def _plural(count: int, one: str, many: str) -> str:
    """`1 table`, `52 tables`."""
    return f"{count} {one}" if count == 1 else f"{count} {many}"


def _pretty(day: date) -> str:
    """`31 Dec 2025`."""
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def _article(data_type: str) -> str:
    """`An` for vowel sounds, `A` otherwise."""
    return "An" if data_type[:1].lower() in "aeiou" else "A"


def _write_table(ctx: StepContext, table: _Table, taken: set[str], rows: int | None) -> None:
    """The `table` and `column` entries for one scanned object."""
    shown = _display(table.schema, table.name, taken)
    columns = _plural(len(table.columns), "column", "columns")
    kind_word = "view (a saved query)" if table.is_view else "table"
    store.upsert_entry(
        ctx.session,
        ctx.version_id,
        table_key(table.schema, table.name),
        "table",
        shown,
        f"A {kind_word} with {_rough(rows)} and {columns}. Charie explains it in a later step.",
        {
            "schema": table.schema,
            "name": table.name,
            "is_view": table.is_view,
            "row_estimate": rows,
            "comment": table.comment,
            "primary_key": table.primary_key,
            "foreign_keys": table.foreign_keys,
            "columns": [column.name for column in table.columns],
        },
        "guessed",
        [SOURCE_STRUCTURE],
        REASON_SCANNED,
    )
    for column in table.columns:
        store.upsert_entry(
            ctx.session,
            ctx.version_id,
            column_key(table.schema, table.name, column.name),
            "column",
            f"{shown}.{column.name}",
            f"{_article(column.data_type)} {column.data_type} column in {shown}."
            " Charie explains it in a later step.",
            {
                "schema": column.schema,
                "table": column.table,
                "name": column.name,
                "position": column.position,
                "data_type": column.data_type,
                "nullable": column.nullable,
                "is_primary_key": column.is_primary_key,
                "is_unique": column.is_unique,
                "comment": column.comment,
            },
            "guessed",
            [SOURCE_STRUCTURE],
            REASON_SCANNED,
        )


def _row_count(ctx: StepContext, table: _Table) -> int | None:
    """`reltuples`, or a real count for views and fresh tables; null when slow."""
    if table.reltuples is not None and table.reltuples > 0 and not table.is_view:
        return int(table.reltuples)
    ref = table_ref(table.schema, table.name)
    try:
        result = _run_query(
            ctx, f"Count the rows of {table.schema}.{table.name}", f"SELECT count(*) FROM {ref}"
        )
    except ConnectorError as err:
        if err.code == "query_timeout":
            return None
        raise
    return int(result.rows[0][0])


def _date_expression(column: _Column, zone: str) -> str:
    """The column as a date: time zones become dates in the owner's zone."""
    ref = quote_ident(column.name)
    if column.data_type == "timestamp with time zone":
        return f"({ref} AT TIME ZONE {quote_literal(zone)})::date"
    if column.data_type == "date":
        return ref
    return f"{ref}::date"


def _date_query(table: _Table, zone: str, sampled: bool) -> str:
    """One row: the row count plus min, max and fill of each date column."""
    dated = [column for column in table.columns if column.data_type in _DATE_TYPES]
    ref = table_ref(table.schema, table.name)
    if sampled:
        inner = f"SELECT {', '.join(quote_ident(column.name) for column in dated)} FROM {ref}"
        if table.is_view:
            inner += " LIMIT 200000"
        else:
            inner += " TABLESAMPLE SYSTEM (1) REPEATABLE (42)"
        source = f"({inner}) AS _sample"
    else:
        source = ref
    parts = ["count(*) AS n"]
    for number, column in enumerate(dated):
        # The sampled subquery keeps the same column names, so one
        # expression works for the full query and the sampled retry.
        expression = _date_expression(column, zone)
        parts.append(f"count({expression}) AS n_{number}")
        parts.append(f"min({expression}) AS min_{number}")
        parts.append(f"max({expression}) AS max_{number}")
    return f"SELECT {', '.join(parts)} FROM {source}"


def _measure_dates(ctx: StepContext, table: _Table, zone: str) -> tuple[dict | None, bool]:
    """The `data_range` details for one table, or None; and if sampled."""
    dated = [column for column in table.columns if column.data_type in _DATE_TYPES]
    if not dated:
        return None, False
    purpose = f"Measure the dates of {table.schema}.{table.name}"
    try:
        result = _run_query(ctx, purpose, _date_query(table, zone, sampled=False))
        exact = True
    except ConnectorError as err:
        if err.code != "query_timeout":
            raise
        try:
            result = _run_query(ctx, purpose, _date_query(table, zone, sampled=True))
            exact = False
        except ConnectorError as retry_err:
            if retry_err.code == "query_timeout":
                return None, False
            raise
    today = datetime.now(UTC).date()
    measured = []
    for number, column in enumerate(dated):
        non_empty = int(result.rows[0][1 + number * 3])
        first = result.rows[0][2 + number * 3]
        last = result.rows[0][3 + number * 3]
        measured.append(
            {
                "column": column.name,
                "date_from": first.isoformat() if first is not None else None,
                "date_to": last.isoformat() if last is not None else None,
                "non_empty": bool(non_empty),
                "fill": non_empty,
            }
        )
    candidates = [
        (item, dated[position])
        for position, item in enumerate(measured)
        if item["fill"] and item["date_to"] is not None and item["date_to"] <= today.isoformat()
    ]
    if not candidates:
        return None, exact
    best_fill = max(item["fill"] for item, _ in candidates)
    best = next(item for item, _ in candidates if item["fill"] == best_fill)
    column = next(column for item, column in candidates if item == best)
    for item in measured:
        del item["fill"]
    return (
        {
            "table": f"{table.schema}.{table.name}",
            "date_column": column.name,
            "date_from": best["date_from"],
            "date_to": best["date_to"],
            "exact": exact,
            "columns": measured,
        },
        exact,
    )


def make_jobs(ctx: StepContext) -> list[dict]:
    """One scan job, or none when no database is connected."""
    if ctx.connector is None:
        return []
    return [{}]


def run_job(info, ctx: StepContext) -> None:
    """Read every object, write its entries, measure its dates."""
    tables = _objects(ctx)
    # Only names in two or more schemas show the schema in front.
    dupes = {
        name
        for name in {table.name for table in tables}
        if sum(1 for table in tables if table.name == name) > 1
    }
    rows: dict[tuple[str, str], int | None] = {}
    for table in tables:
        rows[(table.schema, table.name)] = _row_count(ctx, table)
        _write_table(ctx, table, dupes, rows[(table.schema, table.name)])
    views = sum(1 for table in tables if table.is_view)
    found_tables = len(tables) - views
    column_count = sum(len(table.columns) for table in tables)
    ctx.say(
        "found",
        f"Found {_plural(found_tables, 'table', 'tables')}"
        f" and {_plural(views, 'view', 'views')},"
        f" with {_plural(column_count, 'column', 'columns')}.",
    )
    forbidden = forbidden_tables(ctx.session, ctx.version_id)
    for full in sorted(forbidden):
        ctx.say(
            "info",
            f"Your notes say never to use {full}. I'll list it, but I won't study it.",
        )
    zone = get_setting(ctx.session, "time_zone") or "UTC"
    ranged: dict[str, int] = {}
    for table in tables:
        if f"{table.schema}.{table.name}" in forbidden:
            continue
        details, exact = _measure_dates(ctx, table, zone)
        if details is None:
            continue
        store.upsert_entry(
            ctx.session,
            ctx.version_id,
            data_range_key(table.schema, table.name),
            "data_range",
            f"Dates in {_display(table.schema, table.name, dupes)}",
            f"The data in {_display(table.schema, table.name, dupes)}"
            f" goes from {_pretty(date.fromisoformat(details['date_from']))}"
            f" to {_pretty(date.fromisoformat(details['date_to']))}"
            f" (column {details['date_column']}).",
            details,
            "checked",
            [
                {
                    "type": "query",
                    "text": "Measured the first and last dates",
                    "sql": _date_query(table, zone, sampled=not exact),
                }
            ],
            REASON_SCANNED,
        )
        if not exact:
            ctx.say(
                "info",
                f"{table.name} took too long to read in full, so I measured its dates on a sample.",
            )
        end = details["date_to"]
        known = rows.get((table.schema, table.name)) or 0
        ranged[end] = ranged.get(end, 0) + known
    if ranged:
        # The busiest end date wins; ties go to the later date.
        through = max(ranged, key=lambda day: (ranged[day], day))
        through_date = datetime.fromisoformat(through).replace(tzinfo=UTC)
        ctx.say("found", f"The newest data is from {_pretty(through_date.date())}.")
    else:
        through_date = None
    _remove_gone(ctx, tables)
    _save_source(ctx, tables, views, column_count, rows, through_date)


def _remove_gone(ctx: StepContext, tables: list[_Table]) -> None:
    """Drop `table`, `column` and `data_range` entries for vanished objects."""
    kept = {(table.schema, table.name) for table in tables}
    for entry in store.list_entries(ctx.session, ctx.version_id):
        if entry.kind not in ("table", "column", "data_range"):
            continue
        details = entry.details if isinstance(entry.details, dict) else {}
        if entry.kind == "table":
            full = (details.get("schema") or "", details.get("name") or "")
        elif entry.kind == "column":
            full = (details.get("schema") or "", details.get("table") or "")
        else:
            schema, _, name = (details.get("table") or "").partition(".")
            full = (schema, name)
        if full not in kept:
            store.remove_entry(ctx.session, ctx.version_id, entry.key, REASON_GONE)


def _save_source(
    ctx: StepContext,
    tables: list[_Table],
    views: int,
    column_count: int,
    rows: dict[tuple[str, str], int | None],
    through_date: datetime | None,
) -> None:
    """`data_through`, `checked_at` and the counts on the source row."""
    if ctx.source is None:
        return
    ctx.source.data_through = through_date
    ctx.source.checked_at = datetime.now(UTC)
    is_view = {(table.schema, table.name): table.is_view for table in tables}
    ctx.source.details = {
        **(ctx.source.details or {}),
        "table_count": len(tables) - views,
        "view_count": views,
        "column_count": column_count,
        "total_rows": sum(
            count or 0 for full, count in rows.items() if not is_view.get(full, False)
        ),
    }


def finish_step(ctx: StepContext) -> None:
    """The bare counts, for the run summary."""
    tables = views = columns = 0
    for entry in store.list_entries(ctx.session, ctx.version_id):
        if entry.kind == "table":
            details = entry.details if isinstance(entry.details, dict) else {}
            if details.get("is_view"):
                views += 1
            else:
                tables += 1
        elif entry.kind == "column":
            columns += 1
    ctx.say(
        "found",
        f"{_plural(tables, 'table', 'tables')},"
        f" {_plural(views, 'view', 'views')}"
        f" and {_plural(columns, 'column', 'columns')}",
    )


STRUCTURE_STEP = Step(
    name="structure",
    title="Study the database structure",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="There's no database connected yet, so I skipped this step.",
)

register_step(STRUCTURE_STEP)
register_step_handler("structure")
