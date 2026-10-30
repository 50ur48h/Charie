"""Step 4: find how tables connect, and test each link on the data (P07.8).

Candidates come from the draft entries -- declared foreign keys plus
columns named like another table's key -- and each one is tested with a
count query: how many rows find their match, and is it one-to-one or
many-to-one. Kept links feed the checker's double-counting rule.
"""

from datetime import UTC, datetime

from charie.learner.columns import family
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
from charie.shared.knowledge.keys import link_key, table_key

JOB_KIND = "test_link"

REASON_TESTED = "Tested how many rows match"
REASON_DECLARED = "Declared as a foreign key in the database"
REASON_GONE = "This link wasn't found again"

SOURCE_QUERY = {"type": "query", "text": REASON_TESTED}
SOURCE_DECLARED = {"type": "structure", "text": REASON_DECLARED}

KEEP_CHECKED_SHARE = 0.99
KEEP_GUESS_SHARE = 0.90


def _plural(count: int, one: str, many: str) -> str:
    """`1 table`, `52 tables`."""
    return f"{count} {one}" if count == 1 else f"{count} {many}"


def _name_variants(name: str) -> set[str]:
    """`restaurants` also answers to `restaurant`; `categories` to `category`."""
    found = {name}
    if len(name) > 1 and name.endswith("s"):
        found.add(name[:-1])
    if name.endswith("ies"):
        found.add(name[:-3] + "y")
    return found


def find_candidates(
    tables: dict[str, dict], columns: dict[tuple[str, str], dict], forbidden: set[str]
) -> list[dict]:
    """Possible links from table and column entries; no database queries.

    `tables` maps `schema.table` to its details; `columns` maps
    `(schema, table)` to `{column: details}`.
    """
    names = [full for full in tables if full not in forbidden and not tables[full].get("is_view")]
    known = set(names)
    families: dict[tuple[str, str, str], str] = {}
    for (schema, table), cols in columns.items():
        for column, details in cols.items():
            families[(schema, table, column)] = family(details.get("data_type") or "")
    candidates = []
    for full in names:
        schema, _, name = full.partition(".")
        details = tables[full]
        from_keys = {
            column
            for key in details.get("foreign_keys") or []
            for column in key.get("columns") or []
        }
        for key in details.get("foreign_keys") or []:
            to_full = key.get("ref_table") or ""
            if to_full not in known:
                continue
            from_columns = [
                column
                for column in key.get("columns") or []
                if column in columns.get((schema, name), {})
            ]
            to_schema, _, to_name = to_full.partition(".")
            to_columns = [
                column
                for column in key.get("ref_columns") or []
                if column in columns.get((to_schema, to_name), {})
            ]
            if not from_columns or len(from_columns) != len(to_columns):
                continue
            candidates.append(
                {
                    "from_table": full,
                    "from_columns": from_columns,
                    "to_table": to_full,
                    "to_columns": to_columns,
                    "via": "fk",
                }
            )
        for column in columns.get((schema, name), {}):
            if column in from_keys:
                continue
            from_family = families.get((schema, name, column), "other")
            if from_family in ("other", "json", "xml", "geometric"):
                continue
            same = None
            others = []
            for other in names:
                if other == full:
                    continue
                pk = tables[other].get("primary_key") or []
                if len(pk) != 1:
                    continue
                if not _matches(column, other, pk[0]):
                    continue
                other_schema, _, other_name = other.partition(".")
                if families.get((other_schema, other_name, pk[0]), "other") != from_family:
                    continue
                if other_schema == schema:
                    same = (other, list(pk))
                else:
                    others.append((other, list(pk)))
            if same is not None:
                other, to_columns = same
            elif len(others) == 1:
                other, to_columns = others[0]
            else:
                continue
            candidates.append(
                {
                    "from_table": full,
                    "from_columns": [column],
                    "to_table": other,
                    "to_columns": to_columns,
                    "via": "name",
                }
            )
    seen = set()
    unique = []
    for candidate in candidates:
        mark = (
            candidate["from_table"],
            ",".join(candidate["from_columns"]),
            candidate["to_table"],
            ",".join(candidate["to_columns"]),
        )
        if mark not in seen:
            seen.add(mark)
            unique.append(candidate)
    return unique


def _matches(column: str, other: str, key: str) -> bool:
    """`restaurant_id` points at `restaurants.id`; a bare key matches itself."""
    other_name = other.rpartition(".")[2]
    if any(column == f"{variant}_{key}" for variant in _name_variants(other_name)):
        return True
    return column == key and key != "id"


def make_jobs(ctx: StepContext) -> list[dict]:
    """One job per candidate link; entries only, no database queries."""
    return find_candidates(
        _tables(ctx), _columns(ctx), forbidden_tables(ctx.session, ctx.version_id)
    )


def _tables(ctx: StepContext) -> dict[str, dict]:
    """Draft table entries by `schema.table`."""
    found = {}
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("schema") and details.get("name"):
            found[f"{details['schema']}.{details['name']}"] = details
    return found


def _columns(ctx: StepContext) -> dict[tuple[str, str], dict]:
    """Draft column entries by `(schema, table)`."""
    found: dict[tuple[str, str], dict] = {}
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["column"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("schema") and details.get("table") and details.get("name"):
            found.setdefault((details["schema"], details["table"]), {})[details["name"]] = details
    return found


def _test_query(candidate: dict, source: str) -> str:
    """Empty, non-empty, different and orphan counts for one candidate."""
    cols = [quote_ident(column) for column in candidate["from_columns"]]
    to_cols = [quote_ident(column) for column in candidate["to_columns"]]
    to_ref = table_ref(*candidate["to_table"].split("."))
    rows = ", ".join(f"a.{column}" for column in cols)
    pairs = " AND ".join(f"b.{to_col} = a.{col}" for col, to_col in zip(cols, to_cols, strict=True))
    empty = " OR ".join(f"a.{column} IS NULL" for column in cols)
    return (
        f"SELECT count(*) AS n, count(*) FILTER (WHERE {empty}) AS empty_from,"
        f" count(DISTINCT ({rows})) AS different,"
        f" count(*) FILTER (WHERE NOT ({empty}) AND NOT EXISTS"
        f" (SELECT 1 FROM {to_ref} AS b WHERE {pairs})) AS orphans"
        f" FROM {source} AS a"
    )


def run_job(info, ctx: StepContext) -> None:
    """Test one candidate on the data; keep it, guess it, or drop it."""
    candidate = {
        "from_table": info.payload.get("from_table", ""),
        "from_columns": list(info.payload.get("from_columns") or []),
        "to_table": info.payload.get("to_table", ""),
        "to_columns": list(info.payload.get("to_columns") or []),
        "via": info.payload.get("via", "name"),
    }
    from_schema, _, from_name = candidate["from_table"].partition(".")
    shown = _shown(ctx, from_schema, from_name)
    purpose = f"Test the link {candidate['from_table']} \u2192 {candidate['to_table']}"
    sql = _test_query(candidate, table_ref(from_schema, from_name))
    try:
        row = run_query(ctx, purpose, sql).rows[0]
    except ConnectorError as err:
        if err.code != "query_timeout":
            raise
        try:
            source = f"{table_ref(from_schema, from_name)} TABLESAMPLE SYSTEM (1) REPEATABLE (42)"
            sql = _test_query(candidate, source)
            row = run_query(ctx, purpose, sql).rows[0]
        except ConnectorError as retry_err:
            if retry_err.code == "query_timeout":
                raise SkipItem(f"{shown} took too long to test, so I skipped it.") from retry_err
            raise
        is_sampled = True
    else:
        is_sampled = False
    total, empty_from, different, orphans = (int(value or 0) for value in row)
    non_empty = total - empty_from
    key = link_key(
        from_schema,
        from_name,
        candidate["from_columns"],
        *candidate["to_table"].split("."),
        candidate["to_columns"],
    )
    if not non_empty:
        store.remove_entry(ctx.session, ctx.version_id, key, REASON_GONE)
        return
    share = 1 - orphans / non_empty
    if share >= KEEP_CHECKED_SHARE:
        confidence = "checked"
    elif share >= KEEP_GUESS_SHARE or candidate["via"] == "fk":
        confidence = "guessed"
    else:
        store.remove_entry(ctx.session, ctx.version_id, key, REASON_GONE)
        if candidate["via"] == "name":
            cols = "+".join(candidate["from_columns"])
            ctx.say(
                "info",
                f"{shown}.{cols} looked like a link to"
                f" {_shown(ctx, *candidate['to_table'].split('.'))},"
                f" but only {share:.0%} of rows match, so it isn't one.",
            )
        return
    _write_link(
        ctx,
        candidate,
        key,
        shown,
        confidence,
        share,
        orphans,
        empty_from,
        is_sampled,
        different,
        non_empty,
        sql,
    )


def _shown(ctx: StepContext, schema: str, name: str) -> str:
    """The table's display title, or `schema.table` when it has no entry."""

    entry = store.get_entry(ctx.session, ctx.version_id, table_key(schema, name))
    if entry is not None:
        return entry.title
    return f"{schema}.{name}"


def _write_link(
    ctx,
    candidate,
    key,
    shown,
    confidence,
    share,
    orphans,
    empty_from,
    sampled,
    different,
    non_empty,
    sql,
) -> None:
    """The kept link: meaning, numbers, sources, confidence."""
    to_shown = _shown(ctx, *candidate["to_table"].split("."))
    cols = "+".join(candidate["from_columns"])
    to_cols = "+".join(candidate["to_columns"])
    one_to_one = non_empty > 0 and different == non_empty
    if one_to_one:
        meaning = (
            f"Each row of {shown} matches at most one row of {to_shown}, through {cols}."
            f" Tested: {share:.0%} of rows match."
        )
    else:
        meaning = (
            f"Each row of {shown} points to one row of {to_shown}, through {cols}."
            " Many rows can point to the same row."
            f" Tested: {share:.0%} of rows match."
        )
    sources = [{**SOURCE_QUERY, "sql": sql}]
    if candidate["via"] == "fk":
        sources.append(dict(SOURCE_DECLARED))
    details = {
        "from_table": candidate["from_table"],
        "to_table": candidate["to_table"],
        "from_columns": candidate["from_columns"],
        "to_columns": candidate["to_columns"],
        "found_by": "foreign_key" if candidate["via"] == "fk" else "matching_name",
        "cardinality": "one_to_one" if one_to_one else "many_to_one",
        "match_share": share,
        "orphans": orphans,
        "empty_from": empty_from,
        "sampled": sampled,
        "tested_at": datetime.now(UTC).isoformat(),
    }
    store.upsert_entry(
        ctx.session,
        ctx.version_id,
        key,
        "link",
        f"{shown}.{cols} \u2192 {to_shown}.{to_cols}",
        meaning,
        details,
        confidence,
        sources,
        REASON_TESTED,
    )
    ctx.say("found", f"Linked {shown} to {to_shown} through {cols}: {share:.0%} of rows match.")
    if confidence == "guessed":
        ctx.say(
            "warning",
            f"{shown}.{cols} matches {to_shown}.{to_cols} for only {share:.0%} of rows."
            " I'll keep it as a guess.",
        )


def finish_step(ctx: StepContext) -> None:
    """Links no candidate makes any more are gone; then the count line."""
    candidates = find_candidates(
        _tables(ctx), _columns(ctx), forbidden_tables(ctx.session, ctx.version_id)
    )
    kept = set()
    for candidate in candidates:
        from_schema, _, from_name = candidate["from_table"].partition(".")
        kept.add(
            link_key(
                from_schema,
                from_name,
                candidate["from_columns"],
                *candidate["to_table"].split("."),
                candidate["to_columns"],
            )
        )
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["link"]):
        if entry.key not in kept:
            store.remove_entry(ctx.session, ctx.version_id, entry.key, REASON_GONE)
    checked = total = 0
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["link"]):
        total += 1
        if entry.confidence == "checked":
            checked += 1
    ctx.say("found", f"{_plural(total, 'link', 'links')} between tables ({checked} checked)")


LINKS_STEP = Step(
    name="links",
    title="Find how tables connect",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="There's nothing to connect.",
)

register_step(LINKS_STEP)
register_step_handler("links")
