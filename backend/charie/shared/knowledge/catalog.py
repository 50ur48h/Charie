"""The SQL checker's catalog, built from the knowledge entries (P07.5).

Allowed tables come from the `table` entries; hard rules add the
forbidden tables and the required filters. A rule naming a table that
isn't in the knowledge is left out; a name without a schema matches
that table name in any known schema.
"""

from charie.shared.knowledge.store import list_entries
from charie.shared.safety.catalog import Catalog, RequiredFilter, normalize_table


def _known_tables(session, version_id: int) -> list[str]:
    """Every `table` entry, as `schema.table`."""
    tables = []
    for entry in list_entries(session, version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        schema = details.get("schema") or ""
        name = details.get("name") or ""
        if schema and name:
            tables.append(normalize_table(f"{schema}.{name}"))
    return tables


def _rule_tables(rule_table: str, known: list[str]) -> list[str]:
    """The known tables a rule names: the exact one, or every schema's."""
    if not rule_table:
        return []
    if "." in rule_table:
        full = normalize_table(rule_table)
        return [full] if full in known else []
    bare = rule_table.strip().lower()
    return sorted({full for full in known if full.split(".", 1)[1] == bare})


def _literal(value: str) -> str:
    """A SQL literal: bare numbers, quoted text."""
    try:
        int(value)
        return value
    except ValueError:
        pass
    try:
        float(value)
        return value
    except ValueError:
        pass
    return "'" + value.replace("'", "''") + "'"


def _filter_sql(table: str, column: str, values: list[str], keep: bool) -> str | None:
    """`orders.status = 'completed'`, `orders.id NOT IN (9001, 9002)`.

    Table-qualified like the checker's own filters, so its alias handling
    applies; none without values.
    """
    if not table or not column or not values:
        return None
    short = table.split(".", 1)[1] if "." in table else table
    first = f"{short}.{column}"
    if len(values) == 1:
        return f"{first} = {_literal(values[0])}" if keep else f"{first} <> {_literal(values[0])}"
    joined = ", ".join(_literal(value) for value in values)
    return f"{first} IN ({joined})" if keep else f"{first} NOT IN ({joined})"


def _rule_entries(session, version_id: int) -> list:
    """The `rule` entries, in knowledge order."""
    return list_entries(session, version_id, kinds=["rule"])


def forbidden_tables(session, version_id: int, known: list[str] | None = None) -> set[str]:
    """Tables a `never_use_table` rule forbids (P07.6 lists them anyway).

    Matches rules against the scanned `table` entries, or against the
    given `known` names when the entries are not written yet.
    """
    if known is None:
        known = _known_tables(session, version_id)
    forbidden: set[str] = set()
    for entry in _rule_entries(session, version_id):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("rule_type") != "never_use_table":
            continue
        forbidden.update(_rule_tables(details.get("table") or "", known))
    return forbidden


def build_catalog(session, version_id: int) -> Catalog:
    """P05.12's catalog from one knowledge version."""
    known = _known_tables(session, version_id)
    forbidden: set[str] = set()
    required: list[RequiredFilter] = []
    for entry in _rule_entries(session, version_id):
        details = entry.details if isinstance(entry.details, dict) else {}
        rule_type = details.get("rule_type")
        if rule_type == "never_use_table":
            forbidden.update(_rule_tables(details.get("table") or "", known))
        elif rule_type in ("always_filter", "exclude_values"):
            tables = _rule_tables(details.get("table") or "", known)
            if not tables:
                continue
            sql = _filter_sql(
                tables[0],
                details.get("column") or "",
                details.get("values") or [],
                rule_type == "always_filter",
            )
            if sql is None:
                continue
            for full in tables:
                required.append(RequiredFilter(table=full, sql=sql, reason=entry.title))
    return Catalog(
        tables=known,
        forbidden_tables=sorted(forbidden),
        required_filters=required,
    )
