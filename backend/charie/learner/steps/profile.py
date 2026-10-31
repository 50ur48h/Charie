"""Step 3: profile every column, from a sample when the table is big (P07.7).

One query per table counts and bounds every column; a second query per
column keeps the most common values (never in strict mode); patterns come
from a short read of text values. Dates reuse the structure scan's exact
range. A table that takes too long is skipped, not failed.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from charie.learner.columns import family
from charie.learner.patterns import main_pattern
from charie.learner.sql import quote_ident, table_ref
from charie.learner.steps.base import (
    SkipItem,
    Step,
    StepContext,
    register_step,
    register_step_handler,
    run_query,
)
from charie.shared.connectors.base import ConnectorError
from charie.shared.knowledge import store
from charie.shared.knowledge.catalog import forbidden_tables
from charie.shared.knowledge.keys import data_range_key, table_key

JOB_KIND = "profile_table"

REASON_PROFILED = "Measured from the data"
SOURCE_PROFILE = {"type": "profile", "text": REASON_PROFILED}

SAMPLE_ABOVE_ROWS = 200_000
SAMPLE_TARGET_ROWS = 200_000
PATTERN_VALUES = 200
PATTERN_MAX_LENGTH = 40
TOP_VALUES_LIMIT = 10
TOP_VALUES_MAX_DISTINCT = 1_000
TOP_VALUE_CUT = 100

_SKIP_FAMILIES = ("json", "xml", "geometric")


def _jsonable(value):
    """A stat the knowledge base can store as JSON."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _sample_source(ref: str, rows: int | None, is_view: bool) -> tuple[str, bool]:
    """The FROM clause: the table, a repeatable sample, or a view's head."""
    if rows is not None and rows > SAMPLE_ABOVE_ROWS:
        if is_view:
            return f"(SELECT * FROM {ref} LIMIT {SAMPLE_TARGET_ROWS}) AS _sample", True
        percent = min(max(SAMPLE_TARGET_ROWS / rows * 100, 0.1), 100)
        return f"{ref} TABLESAMPLE SYSTEM ({percent:g}) REPEATABLE (42)", True
    return ref, False


def _query_one(
    names: list[str], families: list[str], strict: bool, source: str
) -> tuple[str, list]:
    """One query per table: counts, bounds and lengths for every column."""
    parts = ["count(*) AS n"]
    plan: list[tuple[str, int]] = []
    for number, (name, kind) in enumerate(zip(names, families, strict=True)):
        ref = quote_ident(name)
        if kind == "text":
            parts.append(f"count(NULLIF({ref}, '')) AS ne_{number}")
        else:
            parts.append(f"count({ref}) AS ne_{number}")
        plan.append(("ne", number))
        if kind not in _SKIP_FAMILIES:
            parts.append(f"count(DISTINCT {ref}) AS d_{number}")
            plan.append(("d", number))
        if kind in ("integer", "numeric", "time") or (kind == "text" and not strict):
            parts.append(f"min({ref}) AS mn_{number}")
            parts.append(f"max({ref}) AS mx_{number}")
            plan.append(("mn", number))
            plan.append(("mx", number))
        if kind == "text":
            parts.append(f"min(char_length({ref})) AS ln_{number}")
            parts.append(f"max(char_length({ref})) AS lx_{number}")
            plan.append(("ln", number))
            plan.append(("lx", number))
    return f"SELECT {', '.join(parts)} FROM {source}", plan


def _top_values_query(name: str, source: str) -> str:
    """The most common non-empty values of one column, ties alphabetical."""
    ref = quote_ident(name)
    return (
        f"SELECT {ref} AS v, count(*) AS n FROM {source}"
        f" WHERE {ref} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1"
        f" LIMIT {TOP_VALUES_LIMIT}"
    )


def _pattern_query(name: str, source: str) -> str:
    """Up to 200 non-empty text values, for the shape check."""
    ref = quote_ident(name)
    return (
        f"SELECT {ref} FROM {source} WHERE {ref} IS NOT NULL AND {ref} <> '' LIMIT {PATTERN_VALUES}"
    )


def _range_dates(session, version_id: int, schema: str, name: str) -> dict[str, tuple]:
    """Each date column's exact dates, from the structure scan's range."""
    entry = store.get_entry(session, version_id, data_range_key(schema, name))
    details = entry.details if entry is not None and isinstance(entry.details, dict) else {}
    found = {}
    for item in details.get("columns") or []:
        if isinstance(item, dict) and item.get("column"):
            found[item["column"]] = (item.get("date_from"), item.get("date_to"))
    return found


def _plural(count: int, one: str, many: str) -> str:
    """`1 table`, `52 tables`."""
    return f"{count} {one}" if count == 1 else f"{count} {many}"


def make_jobs(ctx: StepContext) -> list[dict]:
    """One job per table entry in the draft, except forbidden tables."""
    forbidden = forbidden_tables(ctx.session, ctx.version_id)
    jobs = []
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        full = f"{details.get('schema') or ''}.{details.get('name') or ''}"
        if full in forbidden:
            ctx.say("info", f"Skipping {full}: your notes say never to use it.")
            continue
        jobs.append({"table": full})
    return jobs


def run_job(info, ctx: StepContext) -> None:
    """Profile one table: count it, keep top values and shapes, write it down."""
    full = info.payload.get("table", "")
    schema, _, name = full.partition(".")
    table_entry = store.get_entry(ctx.session, ctx.version_id, table_key(schema, name))
    if table_entry is None:
        return
    shown = table_entry.title
    tdetails = table_entry.details if isinstance(table_entry.details, dict) else {}
    columns = {
        (details.get("name") or ""): entry
        for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["column"])
        for details in [entry.details if isinstance(entry.details, dict) else {}]
        if details.get("schema") == schema and details.get("table") == name
    }
    names = [name for name in (tdetails.get("columns") or []) if name in columns]
    families = [family((columns[name].details or {}).get("data_type") or "") for name in names]
    dated = _range_dates(ctx.session, ctx.version_id, schema, name)
    ref = table_ref(schema, name)
    source, sampled = _sample_source(ref, tdetails.get("row_estimate"), tdetails.get("is_view"))
    try:
        sql, plan = _query_one(names, families, ctx.strict_mode, source)
        row = run_query(ctx, f"Profile {full}", sql).rows[0]
    except ConnectorError as err:
        if err.code == "query_timeout":
            raise SkipItem(f"{shown} took too long to look at, so I skipped it.") from err
        raise
    seen = int(row[0])
    stats: dict[str, dict] = {}
    for position, (kind, number) in enumerate(plan, start=1):
        stats.setdefault(names[number], {})[kind] = row[position]
    profiles = {}
    for name, kind in zip(names, families, strict=True):
        found = stats.get(name, {})
        non_empty = int(found.get("ne", 0) or 0)
        distinct = found.get("d")
        distinct = int(distinct) if distinct is not None else None
        empty = seen - non_empty
        profiles[name] = {
            "rows_seen": seen,
            "sampled": seen if sampled else None,
            "empty": empty,
            "empty_share": empty / seen if seen else 0.0,
            "distinct": distinct,
            "top_values": [],
            "min": _jsonable(found.get("mn")),
            "max": _jsonable(found.get("mx")),
            "min_length": found.get("ln"),
            "max_length": found.get("lx"),
            "pattern": None,
            "pattern_share": 0.0,
            "date_from": None,
            "date_to": None,
            "strict": ctx.strict_mode,
        }
        if kind == "date":
            date_from, date_to = dated.get(name, (None, None))
            profiles[name]["date_from"] = date_from
            profiles[name]["date_to"] = date_to
    if not ctx.strict_mode:
        for name, kind in zip(names, families, strict=True):
            if kind in _SKIP_FAMILIES:
                continue
            distinct = profiles[name]["distinct"]
            if distinct is None or distinct > TOP_VALUES_MAX_DISTINCT:
                continue
            _read_top_values(ctx, full, shown, source, name, profiles[name])
    for name, kind in zip(names, families, strict=True):
        if kind != "text":
            continue
        _read_pattern(ctx, full, shown, source, name, profiles[name])
    _write_table(ctx, full, shown, table_entry, tdetails, seen, sampled)
    for name in names:
        _write_column(ctx, columns[name], profiles[name])
    if sampled:
        ctx.say("info", f"Looked at {shown}: {len(names)} columns, a sample of 200K rows.")
    else:
        ctx.say("info", f"Looked at {shown}: {len(names)} columns, all {seen} rows.")
    for name in names:
        title = (columns[name].title or name).split(".")[-1]
        label = f"{shown}.{title}"
        if seen and profiles[name]["empty"] == seen:
            ctx.say("found", f"{label} is always empty.")
        pattern = profiles[name]["pattern"]
        if pattern is not None:
            share = profiles[name]["pattern_share"]
            ctx.say("found", f"{label} looks like a code: {pattern} ({share:.0%} of values).")


def _read_top_values(ctx, full, shown, source, name, profile) -> None:
    """The most common values, saved as short text."""
    try:
        rows = run_query(ctx, f"Profile {full}.{name}", _top_values_query(name, source)).rows
    except ConnectorError as err:
        if err.code == "query_timeout":
            raise SkipItem(f"{shown} took too long to look at, so I skipped it.") from err
        raise
    profile["top_values"] = [
        {"value": str(value)[:TOP_VALUE_CUT], "count": int(count)} for value, count in rows
    ]


def _read_pattern(ctx, full, shown, source, name, profile) -> None:
    """The value shape, when 80% of a short text column wears it."""
    try:
        rows = run_query(ctx, f"Profile {full}.{name}", _pattern_query(name, source)).rows
    except ConnectorError as err:
        if err.code == "query_timeout":
            raise SkipItem(f"{shown} took too long to look at, so I skipped it.") from err
        raise
    values = [row[0] for row in rows if isinstance(row[0], str)]
    if not values or sum(len(value) for value in values) / len(values) > PATTERN_MAX_LENGTH:
        return
    pattern, share = main_pattern(values)
    if pattern is not None:
        profile["pattern"] = pattern
        profile["pattern_share"] = share


def _write_table(ctx, full, shown, entry, tdetails, seen, sampled) -> None:
    """The table entry keeps its words; the profile lands in its details."""
    details = {
        **tdetails,
        "profiled_at": datetime.now(UTC).isoformat(),
        "sampled": sampled,
        "rows_profiled": seen,
    }
    sources = list(entry.sources or [])
    if SOURCE_PROFILE not in sources:
        sources.append(SOURCE_PROFILE)
    store.upsert_entry(
        ctx.session,
        ctx.version_id,
        entry.key,
        "table",
        entry.title,
        entry.meaning,
        details,
        entry.confidence,
        sources,
        REASON_PROFILED,
    )


def _write_column(ctx, entry, profile) -> None:
    """The column entry keeps its words; the profile lands in its details."""
    details = dict(entry.details or {})
    details["profile"] = profile
    sources = list(entry.sources or [])
    if SOURCE_PROFILE not in sources:
        sources.append(SOURCE_PROFILE)
    store.upsert_entry(
        ctx.session,
        ctx.version_id,
        entry.key,
        "column",
        entry.title,
        entry.meaning,
        details,
        entry.confidence,
        sources,
        REASON_PROFILED,
    )


def finish_step(ctx: StepContext) -> None:
    """How much got a profile, for the run summary."""
    tables = columns = 0
    for entry in store.list_entries(ctx.session, ctx.version_id):
        details = entry.details if isinstance(entry.details, dict) else {}
        if entry.kind == "table" and details.get("profiled_at"):
            tables += 1
        elif entry.kind == "column" and details.get("profile"):
            columns += 1
    ctx.say(
        "found",
        f"{_plural(tables, 'table', 'tables')} and views, {_plural(columns, 'column', 'columns')}",
    )


PROFILE_STEP = Step(
    name="profile",
    title="Look at the data itself",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="There's nothing to profile.",
)

register_step(PROFILE_STEP)
register_step_handler("profile")
