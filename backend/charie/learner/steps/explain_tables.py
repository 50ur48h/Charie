"""Step 5: the AI explains what each table means, and code checks it (P07.9).

Meanings are the AI's words; everything checkable is code's job: units need
matching types, money needs the owner's currency, links need tested matches,
and no number may appear that the input never used. What fails stays a guess.
"""

import json
from typing import Literal

from pydantic import BaseModel, Field

from charie.learner.columns import family
from charie.learner.number_check import find_new_numbers
from charie.learner.sql import quote_ident, table_ref
from charie.learner.steps.base import (
    SkipItem,
    Step,
    StepContext,
    register_step,
    register_step_handler,
    run_query,
)
from charie.shared.ai.client import get_ai
from charie.shared.connectors.base import ConnectorError
from charie.shared.knowledge import store
from charie.shared.knowledge.catalog import forbidden_tables
from charie.shared.knowledge.keys import name_key, table_key

JOB_KIND = "explain_table"

REASON_EXPLAINED = "Explained by the AI and checked against the data"
SOURCE_AI = {"type": "ai", "text": REASON_EXPLAINED}

NAME_LIST_MAX_ROWS = 1_000
NAME_LIST_READ_LIMIT = 1_001

UnitKind = Literal[
    "money",
    "count",
    "percent",
    "ratio",
    "quantity",
    "duration",
    "date",
    "id",
    "code",
    "text",
    "flag",
    "other",
]


class ExplainColumn(BaseModel):
    """One column's meaning, in the AI's words."""

    name: str = Field(description="The column's name, exactly as in the input.")
    meaning: str = Field(description="What the column means, in one plain sentence.")
    unit: UnitKind = Field(description="What the values measure.")
    unit_name: str = Field(
        default="", description="The unit's name, like dollars; empty when none."
    )
    currency: str = Field(
        default="", description="The three-letter money code; empty for anything else."
    )
    refers_to: str = Field(
        default="", description="The table this column points to; empty when nowhere."
    )


class NameList(BaseModel):
    """How people name rows, when the table is small enough to list."""

    id_column: str = Field(default="", description="The column that names one row.")
    name_column: str = Field(default="", description="The column people say.")


class ExplainTableForm(BaseModel):
    """The fixed form the explain job answers in."""

    table_meaning: str = Field(description="What the table is for, in one plain sentence.")
    grain: str = Field(description="What one row is, for example one order.")
    columns: list[ExplainColumn] = Field(default=[], description="What each column means.")
    name_list: NameList = Field(
        default_factory=NameList, description="How people name rows, when listable."
    )


def _plural(count: int, one: str, many: str) -> str:
    """`1 table`, `52 tables`."""
    return f"{count} {one}" if count == 1 else f"{count} {many}"


def _rule_lines(session, version_id: int, full: str) -> tuple[list[str], list[str]]:
    """Owner rules for one table: its notes, plus every currency and required note."""
    texts = []
    codes = []
    for entry in store.list_entries(session, version_id):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("rule_type") in ("currency", "required_note"):
            texts.append(f"- {entry.title}: {entry.meaning}")
            if details.get("rule_type") == "currency" and details.get("currency"):
                codes.append(details["currency"])
            continue
        tables = details.get("applies_to_tables") or details.get("tables") or []
        if any(table == full or table == full.rpartition(".")[2] for table in tables):
            texts.append(f"- {entry.title}: {entry.meaning}")
    return texts, codes


def build_explain_input(session, version_id: int, table: dict, strict: bool) -> dict:
    """Everything the AI gets: the table, its links, the owner rules, other names."""
    schema, name = table.get("schema") or "", table.get("name") or ""
    full = f"{schema}.{name}"
    columns = []
    for entry in store.list_entries(session, version_id, kinds=["column"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("schema") != schema or details.get("table") != name:
            continue
        profile = details.get("profile") or {}
        top_values = [item.get("value") for item in profile.get("top_values") or []]
        columns.append(
            {
                "name": details.get("name"),
                "type": details.get("data_type"),
                "nullable": details.get("nullable"),
                "comment": details.get("comment") or "",
                "empty_share": profile.get("empty_share"),
                "distinct": profile.get("distinct"),
                "min": profile.get("min"),
                "max": profile.get("max"),
                "top_values": [] if strict else top_values,
                "pattern": profile.get("pattern"),
                "date_from": profile.get("date_from"),
                "date_to": profile.get("date_to"),
            }
        )
    columns.sort(key=lambda column: column["name"] or "")
    touched = []
    for entry in store.list_entries(session, version_id, kinds=["link"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("from_table") != full and details.get("to_table") != full:
            continue
        touched.append(
            {
                "from_table": details.get("from_table"),
                "from_columns": details.get("from_columns"),
                "to_table": details.get("to_table"),
                "to_columns": details.get("to_columns"),
                "cardinality": details.get("cardinality"),
                "match_share": details.get("match_share"),
            }
        )
    others = sorted(
        {
            (entry.details or {}).get("name") or ""
            for entry in store.list_entries(session, version_id, kinds=["table"])
            if isinstance(entry.details, dict)
            and (entry.details or {}).get("schema")
            and f"{(entry.details or {})['schema']}.{(entry.details or {})['name']}" != full
        }
        - {""}
    )
    rules, _ = _rule_lines(session, version_id, full)
    return {
        "table": {
            "name": name,
            "kind": "view" if table.get("is_view") else "table",
            "rows": table.get("row_estimate"),
            "comment": table.get("comment") or "",
            "primary_key": table.get("primary_key") or [],
            "foreign_keys": table.get("foreign_keys") or [],
            "columns": columns,
            "links": touched,
            "other_tables": others,
        },
        "owner_rules": "\n".join(rules) if rules else "(none)",
    }


def _number(value):
    """A real bound, or nothing when the profile has none (or text)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def check_explanation(
    form: ExplainTableForm,
    *,
    columns: dict,
    links: list[dict],
    currency_codes: list[str],
    source_text: str,
) -> dict[str, list[str]]:
    """Every failed check, by column name; columns without failures stay out.

    `columns` maps a name to its family, types and bounds; `links` are the
    kept links from this table, with `from_columns` and both table names.
    """
    failed: dict[str, list[str]] = {}
    by_name = {column.name: column for column in form.columns}

    def fail(name: str, reason: str) -> None:
        failed.setdefault(name, []).append(reason)

    for name, info in columns.items():
        column = by_name.get(name)
        if column is None:
            continue
        kind = info.get("family") or "other"
        smallest, largest = _number(info.get("min")), _number(info.get("max"))
        if column.unit == "money" and kind not in ("integer", "numeric"):
            fail(name, f"Said to be money, but the column holds {kind}.")
        if column.unit == "count":
            if smallest is not None and smallest < 0:
                fail(name, f"Said to be a count, but the smallest value is {smallest}.")
            elif any(value is not None and value != int(value) for value in (smallest, largest)):
                fail(name, "Said to be a count, but the values are not whole numbers.")
        if column.unit == "percent" and smallest is not None and smallest < 0:
            fail(name, f"Said to be a percent, but the smallest value is {smallest}.")
        if column.unit == "duration" and kind not in ("integer", "numeric", "time"):
            fail(name, f"Said to be a duration, but the column holds {kind}.")
        if column.unit == "date" and kind not in ("date", "time"):
            fail(name, f"Said to be a date, but the column holds {kind}.")
        if column.unit == "flag":
            distinct = info.get("distinct")
            if kind != "boolean" and (distinct is None or distinct > 2):
                if distinct is None:
                    fail(name, f"Said to be a flag, but the column holds {kind}.")
                else:
                    fail(name, f"Said to be a flag, but it has {distinct} different values.")
        if column.currency:
            if column.unit != "money":
                fail(name, f"Said to be {column.currency}, but the column is not money.")
            elif currency_codes and column.currency not in currency_codes:
                fail(name, f"Said to be {column.currency}, but money here is {currency_codes[0]}.")
        from_here = [link for link in links if name in (link.get("from_columns") or [])]
        if column.refers_to:
            if not any(
                column.refers_to in (link.get("to_table"), link.get("to_title"))
                for link in from_here
            ):
                fail(name, f"Said to point to {column.refers_to}, but no tested link goes there.")
        elif from_here:
            to = from_here[0].get("to_title") or from_here[0].get("to_table")
            fail(name, f"The data shows {name} points to {to}, but the explanation doesn't say so.")
        new = find_new_numbers([column.meaning], source_text)
        if new:
            fail(name, f"Uses the number {new[0]}, which is not in the input.")
    new_meaning = find_new_numbers([form.table_meaning, form.grain], source_text)
    if new_meaning:
        failed.setdefault("", []).append(
            f"Uses the number {new_meaning[0]}, which is not in the input."
        )
    return failed


def make_jobs(ctx: StepContext) -> list[dict]:
    """One job per table or view in the draft, except forbidden tables."""
    forbidden = forbidden_tables(ctx.session, ctx.version_id)
    jobs = []
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        full = f"{details.get('schema') or ''}.{details.get('name') or ''}"
        if full in forbidden:
            ctx.say("info", f"Skipping {full}: the owner's notes say never to use it.")
            continue
        jobs.append({"table": full})
    return jobs


def run_job(info, ctx: StepContext) -> None:
    """Explain one table: ask the AI, check the reply, write what holds."""

    full = info.payload.get("table", "")
    schema, _, name = full.partition(".")
    table_entry = store.get_entry(ctx.session, ctx.version_id, table_key(schema, name))
    if table_entry is None:
        return
    shown = table_entry.title
    tdetails = table_entry.details if isinstance(table_entry.details, dict) else {}
    asked = _ask(ctx, tdetails, ctx.strict_mode)
    if asked is None:
        return
    form, table_json, owner_rules = asked
    columns = _column_info(ctx, schema, name)
    links = _table_links(ctx, full)
    _, codes = _rule_lines(ctx.session, ctx.version_id, full)
    source_text = json.dumps({"table": table_json, "owner_rules": owner_rules}, sort_keys=True)
    failures = check_explanation(
        form,
        columns=columns,
        links=links,
        currency_codes=codes,
        source_text=source_text,
    )
    table_failures = failures.pop("", [])
    by_name = {column.name: column for column in form.columns}
    known = {name for name in columns if name in by_name}
    missing = [name for name in columns if name not in by_name]  # unknown names are ignored
    name_ok, name_failures = _name_list(ctx, full, shown, tdetails, form.name_list, columns)
    table_failures.extend(name_failures)
    column_confidence = {name: "guessed" if name in failures else "checked" for name in known}
    table_checked = (
        bool(form.table_meaning)
        and not missing
        and all(confidence == "checked" for confidence in column_confidence.values())
        and name_ok
        and not table_failures
    )
    _write_table(ctx, table_entry, tdetails, form, table_checked, table_failures)
    for name in known:
        _write_column(
            ctx,
            full,
            name,
            columns[name],
            by_name[name],
            column_confidence[name],
            failures.get(name, []),
        )
    if missing:
        shown_missing = ", ".join(missing)
        ctx.say(
            "warning",
            f"I couldn't explain {_plural(len(missing), 'column', 'columns')}"
            f" of {shown}: {shown_missing}.",
        )
    if table_checked:
        ctx.say(
            "found",
            f"Explained {shown}: one row is {form.grain}."
            f" All {len(columns)} columns check out against the data.",
        )
    elif [name for name in known if name in failures]:
        bad = [name for name in by_name if name in failures]
        ctx.say(
            "warning",
            f"Explained {shown}, but {len(bad)} don't match the data,"
            f" so they stay guesses: {', '.join(bad)}.",
        )
    elif table_failures:
        ctx.say(
            "warning",
            f"Explained {shown}, but its name list doesn't check out, so it stays a guess.",
        )


def _ask(
    ctx: StepContext, tdetails: dict, strict: bool
) -> tuple[ExplainTableForm, dict, str] | None:
    """The AI's reply with its input, or nothing when it has no entries at all."""
    table_input = build_explain_input(ctx.session, ctx.version_id, tdetails, strict)
    form = get_ai().run(
        "explain_table",
        {"table": table_input["table"], "owner_rules": table_input["owner_rules"]},
        ExplainTableForm,
        app="learner",
        learning_run_id=ctx.run_id,
    )
    if not form.table_meaning and not form.columns:
        return None
    return form, table_input["table"], table_input["owner_rules"]


def _column_info(ctx: StepContext, schema: str, name: str) -> dict:
    """Every column entry of a table, with its family and profile bounds."""
    found = {}
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["column"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("schema") != schema or details.get("table") != name:
            continue
        profile = details.get("profile") or {}
        found[details.get("name")] = {
            "family": family(details.get("data_type") or ""),
            "data_type": details.get("data_type") or "",
            "min": profile.get("min"),
            "max": profile.get("max"),
            "distinct": profile.get("distinct"),
            "entry": entry,
        }
    return found


def _table_links(ctx: StepContext, full: str) -> list[dict]:
    """Kept links from one table, with both table names."""
    found = []
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["link"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("from_table") != full:
            continue
        to_schema, _, to_name = (details.get("to_table") or "").partition(".")
        to_entry = store.get_entry(ctx.session, ctx.version_id, table_key(to_schema, to_name))
        found.append(
            {
                "from_columns": details.get("from_columns") or [],
                "to_table": details.get("to_table"),
                "to_title": to_entry.title if to_entry is not None else details.get("to_table"),
            }
        )
    return found


def _name_list(ctx, full, shown, tdetails, name_list: NameList, columns: dict):
    """The name list, when people name rows and the table is small.

    Returns whether the table can still be checked, plus table-level
    failures. Strict mode, too many rows, or a bad id/name column stops it.
    """
    if not name_list.id_column and not name_list.name_column:
        return True, []
    if ctx.strict_mode:
        ctx.say("info", f"Strict mode is on, so I didn't keep the names in {shown}.")
        return True, []
    rows = tdetails.get("row_estimate")
    if rows is None or rows > NAME_LIST_MAX_ROWS:
        ctx.say("info", f"{shown} has too many rows for a name list, so I skipped it.")
        return True, []
    schema, _, name = full.partition(".")
    id_info = columns.get(name_list.id_column)
    failures = []
    if id_info is None:
        failures.append(f"The name list names {name_list.id_column}, which is not a column.")
    elif name_list.id_column not in (tdetails.get("primary_key") or []) and not (
        id_info["entry"].details or {}
    ).get("is_unique"):
        failures.append(f"The name list's {name_list.id_column} is not a unique column.")
    if name_list.name_column not in columns:
        failures.append(f"The name list names {name_list.name_column}, which is not a column.")
    if failures:
        return False, failures
    sql = (
        f"SELECT {quote_ident(name_list.id_column)} AS id,"
        f" {quote_ident(name_list.name_column)} AS name"
        f" FROM {table_ref(schema, name)} ORDER BY 2 LIMIT {NAME_LIST_READ_LIMIT}"
    )
    try:
        found = run_query(ctx, f"Read the names in {full}", sql).rows
    except ConnectorError as err:
        if err.code == "query_timeout":
            raise SkipItem(f"{shown} took too long to read, so I skipped it.") from err
        raise
    items = [
        {"id": row[0], "name": "" if row[1] is None else str(row[1])}
        for row in found[:NAME_LIST_MAX_ROWS]
    ]
    store.upsert_entry(
        ctx.session,
        ctx.version_id,
        name_key(schema, name),
        "name",
        f"Names in {shown}",
        f"The names in {shown}.{name_list.name_column},"
        " so Charie can match the names people type to rows.",
        {
            "table": full,
            "id_column": name_list.id_column,
            "name_column": name_list.name_column,
            "items": items,
            "truncated": len(found) > NAME_LIST_MAX_ROWS,
        },
        "checked",
        [SOURCE_AI],
        REASON_EXPLAINED,
    )
    return True, []


def _write_table(ctx, table_entry, tdetails, form, table_checked, table_failures) -> None:
    """The table entry keeps its structure; the AI's words land in details."""
    details = dict(tdetails)
    details["grain"] = form.grain
    details["explained"] = True
    details["checks_failed"] = table_failures
    sources = list(table_entry.sources or [])
    if SOURCE_AI not in sources:
        sources.append(SOURCE_AI)
    store.upsert_entry(
        ctx.session,
        ctx.version_id,
        table_entry.key,
        "table",
        table_entry.title,
        form.table_meaning or table_entry.meaning,
        details,
        "checked" if table_checked else "guessed",
        sources,
        REASON_EXPLAINED,
    )


def _write_column(ctx, full, name, info, reply, confidence, failures) -> None:
    """A column entry keeps its structure; the AI's words land in details."""
    entry = info["entry"]
    details = dict(entry.details or {})
    details["unit"] = reply.unit
    details["unit_name"] = reply.unit_name
    details["currency"] = reply.currency
    details["refers_to"] = reply.refers_to
    details["explained"] = True
    details["checks_failed"] = failures
    sources = list(entry.sources or [])
    if SOURCE_AI not in sources:
        sources.append(SOURCE_AI)
    store.upsert_entry(
        ctx.session,
        ctx.version_id,
        entry.key,
        "column",
        entry.title,
        reply.meaning or entry.meaning,
        details,
        confidence,
        sources,
        REASON_EXPLAINED,
    )


def finish_step(ctx: StepContext) -> None:
    """How many tables got an explanation, and how many check out."""
    total = checked = 0
    for entry in store.list_entries(ctx.session, ctx.version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if not details.get("explained"):
            continue
        total += 1
        if entry.confidence == "checked":
            checked += 1
    ctx.say("found", f"{total} tables explained ({checked} checked against the data)")


EXPLAIN_STEP = Step(
    name="explain_tables",
    title="Explain what the tables mean",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="There's nothing to explain.",
)

register_step(EXPLAIN_STEP)
register_step_handler("explain_tables")
