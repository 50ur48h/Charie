"""Rule the SQL before it runs (06): one SELECT, known tables, filters, LIMIT.

Everything here walks sqlglot's tree, never the text.
"""

import sqlglot
from pydantic import BaseModel
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope

from charie.shared.safety.catalog import Catalog, normalize_table

ONE_SELECT = "one_select"
ALLOWED_TABLES = "allowed_tables"
FUNCTIONS = "functions"
REQUIRED_FILTERS = "required_filters"
COUNTING = "counting"
AVERAGING = "averaging"
EXPLICIT_COLUMNS = "explicit-columns"
HEAVY_QUERY = "heavy_query"

_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema")

# Nodes that change data or settings, anywhere in the tree (also inside WITH).
_WRITE_NAMES = (
    (exp.Insert, "INSERT"),
    (exp.Update, "UPDATE"),
    (exp.Delete, "DELETE"),
    (exp.Merge, "MERGE"),
    (exp.Create, "CREATE"),
    (exp.Drop, "DROP"),
    (exp.Alter, "ALTER"),
    (exp.TruncateTable, "TRUNCATE"),
    (exp.Grant, "GRANT"),
    (exp.Copy, "COPY"),
    (exp.Set, "SET"),
)

_STATEMENT_NAMES = {
    exp.Delete: "DELETE",
    exp.Insert: "INSERT",
    exp.Update: "UPDATE",
    exp.Merge: "MERGE",
    exp.Create: "CREATE",
    exp.Drop: "DROP",
    exp.Alter: "ALTER",
    exp.TruncateTable: "TRUNCATE",
    exp.Grant: "GRANT",
    exp.Copy: "COPY",
    exp.Set: "SET",
}

# 06's dangerous functions: exact names, plus these prefixes (`*`).
_DANGEROUS_EXACT = {
    "PG_READ_FILE",
    "PG_READ_BINARY_FILE",
    "PG_LS_DIR",
    "PG_STAT_FILE",
    "SET_CONFIG",
    "CURRENT_SETTING",
    "PG_TERMINATE_BACKEND",
    "PG_CANCEL_BACKEND",
    "PG_RELOAD_CONF",
}
_DANGEROUS_PREFIX = ("PG_SLEEP", "LO_", "DBLINK")

# Every other function must be on this list.
_ALLOWED_FUNCTIONS = {
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "STDDEV",
    "STDDEV_SAMP",
    "STDDEV_POP",
    "VARIANCE",
    "VAR_POP",
    "VAR_SAMP",
    "PERCENTILE_CONT",
    "PERCENTILE_DISC",
    "MODE",
    "BOOL_AND",
    "BOOL_OR",
    "STRING_AGG",
    "ARRAY_AGG",
    "ROW_NUMBER",
    "RANK",
    "DENSE_RANK",
    "NTILE",
    "LAG",
    "LEAD",
    "FIRST_VALUE",
    "LAST_VALUE",
    "PERCENT_RANK",
    "CUME_DIST",
    "COALESCE",
    "NULLIF",
    "GREATEST",
    "LEAST",
    "ROUND",
    "FLOOR",
    "CEIL",
    "CEILING",
    "ABS",
    "SIGN",
    "POWER",
    "SQRT",
    "LN",
    "LOG",
    "EXP",
    "MOD",
    "TRUNC",
    "DIV",
    "DATE_TRUNC",
    "DATE_PART",
    "EXTRACT",
    "AGE",
    "MAKE_DATE",
    "TO_CHAR",
    "TO_DATE",
    "NOW",
    "CURRENT_DATE",
    "CURRENT_TIMESTAMP",
    "LOWER",
    "UPPER",
    "TRIM",
    "LTRIM",
    "RTRIM",
    "LENGTH",
    "SUBSTRING",
    "SUBSTR",
    "REPLACE",
    "CONCAT",
    "LEFT",
    "RIGHT",
    "SPLIT_PART",
    "POSITION",
    "STRPOS",
    "INITCAP",
}


class CheckReport(BaseModel):
    """The checker's verdict: ok with the query to run, or plain reasons."""

    ok: bool
    sql: str
    reasons: list[str]
    rules: list[str]
    tables: list[str]


def check_sql(sql: str, catalog: Catalog, *, max_rows: int = 50_000) -> CheckReport:
    """Check one query against the catalog; collect every failure."""
    reasons: list[str] = []
    rules: list[str] = []
    tables: list[str] = []

    def fail(rule: str, reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)
        if rule not in rules:
            rules.append(rule)

    try:
        trees = [tree for tree in sqlglot.parse(sql, read="postgres") if tree is not None]
    except SqlglotError as err:
        short = str(err).split("\n")[0].strip()
        return CheckReport(
            ok=False,
            sql=sql,
            reasons=[f"Charie couldn't read this query: `{short}`."],
            rules=[ONE_SELECT],
            tables=[],
        )
    if not trees:
        return CheckReport(
            ok=False,
            sql=sql,
            reasons=["Only one query at a time is allowed."],
            rules=[ONE_SELECT],
            tables=[],
        )
    if len(trees) > 1:
        fail(ONE_SELECT, "Only one query at a time is allowed.")

    seen_tables: list[str] = []
    for tree in trees:
        _rule_one_select(tree, fail)
        for name in _rule_tables(tree, catalog, fail):
            if name not in seen_tables:
                seen_tables.append(name)
        _rule_functions(tree, fail)
        _rule_required_filters(tree, catalog, fail)
        _rule_counting(tree, fail)
        _rule_averaging(tree, catalog, fail)
        _rule_explicit_columns(tree, fail)

    if len(trees) == 1 and isinstance(trees[0], exp.Select):
        _apply_limit(trees[0], max_rows)
        rendered = trees[0].sql(dialect="postgres")
    else:
        rendered = sql
    tables = sorted(seen_tables)
    return CheckReport(ok=not reasons, sql=rendered, reasons=reasons, rules=rules, tables=tables)


def _statement_kind(tree: exp.Expression) -> str:
    """`DELETE`, `LOCK`, ... for the "not a SELECT" message."""
    for cls, name in _STATEMENT_NAMES.items():
        if isinstance(tree, cls):
            return name
    word = ""
    for char in tree.sql(dialect="postgres").lstrip().upper():
        if char.isalpha() or char == "_":
            word += char
        else:
            break
    return word or "UNKNOWN"


def _rule_one_select(tree: exp.Expression, fail) -> None:
    """Rule 1: one SELECT (or WITH/UNION of selects), nothing that writes."""
    if not isinstance(tree, (exp.Select, exp.Union)):
        fail(
            ONE_SELECT,
            f"Only SELECT queries are allowed. This one is a `{_statement_kind(tree)}`.",
        )
    whats: list[str] = []
    for cls, name in _WRITE_NAMES:
        if tree.find(cls) is not None and name not in whats:
            whats.append(name)
    if tree.find(exp.Into) is not None and "SELECT … INTO" not in whats:
        whats.append("SELECT … INTO")
    for select in tree.find_all(exp.Select):
        for lock in select.args.get("locks") or []:
            what = "FOR UPDATE" if lock.args.get("update") else "FOR SHARE"
            if what not in whats:
                whats.append(what)
    for what in whats:
        fail(
            ONE_SELECT,
            f"This query tries to change data or settings (`{what}`), which isn't allowed.",
        )


def _direct_tables(scope) -> list:
    """The FROM/JOIN tables of one SELECT (not sub-queries, not CTE bodies)."""
    expression = scope.expression
    if not isinstance(expression, exp.Select):
        return []
    from_ = expression.args.get("from_")
    if from_ is None:
        return []
    nodes = [from_.this]
    nodes.extend(from_.args.get("expressions", []))
    for join in expression.args.get("joins", []):
        nodes.append(join.this)
    return [node for node in nodes if isinstance(node, exp.Table)]


def _rule_tables(tree: exp.Expression, catalog: Catalog, fail) -> list[str]:
    """Rule 2: every table is known, allowed, and really a table."""
    used: list[str] = []
    for scope in traverse_scope(tree):
        ctes = set()
        for source in scope.cte_sources:
            if isinstance(source, str):
                ctes.add(source.lower())
            else:
                ctes.add(str(source).lower())
        for table in _direct_tables(scope):
            if isinstance(table.this, exp.Func):
                func = table.find(exp.Func)
                name = func.sql(dialect="postgres").split("(")[0].strip() if func else "?"
                fail(
                    ALLOWED_TABLES,
                    f"Only tables can be read in FROM; `{name}` isn't one.",
                )
                continue
            full = normalize_table(f"{table.db}.{table.name}" if table.db else table.name)
            if table.name.lower() in ctes:
                continue
            if full not in used:
                used.append(full)
            schema, name = full.split(".", 1)
            if schema in _SYSTEM_SCHEMAS or name.startswith("pg_"):
                fail(ALLOWED_TABLES, f"System tables can't be used: `{full}`.")
            elif full in catalog.forbidden_tables:
                fail(
                    ALLOWED_TABLES,
                    f"This query uses `{full}`, which the owner's rules say never to use.",
                )
            elif full not in catalog.tables:
                fail(
                    ALLOWED_TABLES,
                    f"This query uses `{full}`, which isn't in Charie's list of known tables.",
                )
    return used


def _function_name(node: exp.Func) -> str:
    """The name as Postgres writes it (`DATE_TRUNC` stays `DATE_TRUNC`)."""
    rendered = node.sql(dialect="postgres").split("(")[0].strip().upper()
    return rendered.split(".")[-1]


def _rule_functions(tree: exp.Expression, fail) -> None:
    """Rule 3: no dangerous functions; the rest must be on the list."""
    for node in tree.find_all(exp.Func):
        if isinstance(node, (exp.Case, exp.Cast, exp.If)):
            continue
        name = _function_name(node)
        if not name or any(char.isspace() for char in name):
            continue
        if name in _DANGEROUS_EXACT or name.startswith(_DANGEROUS_PREFIX):
            fail(FUNCTIONS, f"`{name}` is a dangerous function and isn't allowed.")
        elif name not in _ALLOWED_FUNCTIONS:
            fail(
                FUNCTIONS,
                f"The function `{name}` isn't on Charie's list of allowed functions.",
            )


def _unwrap(node: exp.Expression) -> exp.Expression:
    """Strip redundant parentheses for the filter comparison."""
    while isinstance(node, exp.Paren):
        node = node.this
    return node


def _conjuncts(where: exp.Where) -> list:
    """The top-level AND parts of a WHERE (an OR stays whole)."""
    parts: list = []
    stack = [_unwrap(where.this)]
    while stack:
        node = _unwrap(stack.pop())
        if isinstance(node, exp.And):
            stack.append(node.left)
            stack.append(node.right)
        else:
            parts.append(node)
    return parts


def _render(node: exp.Expression) -> str:
    """One normal form: the condition re-read and written by sqlglot."""
    return sqlglot.parse_one(node.sql(dialect="postgres"), read="postgres").sql(dialect="postgres")


def _filter_candidates(filt: exp.Expression, table: str, aliases: set, single_source: bool) -> set:
    """The filter with the table's name swapped for each alias it may wear."""
    short = table.split(".", 1)[1]
    renders = set()
    names = set(aliases) | {short}
    for alias in sorted(names):
        patched = filt.copy()
        for column in patched.find_all(exp.Column):
            if (column.table or "").lower() == short:
                if alias == short:
                    column.set("table", exp.to_identifier(short))
                else:
                    column.set("table", exp.to_identifier(alias))
        renders.add(_render(patched))
    if single_source:
        bare = filt.copy()
        for column in bare.find_all(exp.Column):
            if (column.table or "").lower() == short:
                column.set("table", None)
        renders.add(_render(bare))
    return renders


def _rule_required_filters(tree: exp.Expression, catalog: Catalog, fail) -> None:
    """Rule 4: each required filter sits in the WHERE of every SELECT using it."""
    if not catalog.required_filters:
        return
    by_table: dict[str, list] = {}
    for filt in catalog.required_filters:
        by_table.setdefault(filt.table, []).append(filt)
    for scope in traverse_scope(tree):
        if not isinstance(scope.expression, exp.Select):
            continue
        tables = _direct_tables(scope)
        real = []
        ctes = {str(source).lower() for source in scope.cte_sources}
        for table in tables:
            if isinstance(table.this, exp.Func):
                continue
            if table.name.lower() in ctes:
                continue
            full = normalize_table(f"{table.db}.{table.name}" if table.db else table.name)
            alias = table.alias or table.name
            real.append((full, alias.lower()))
        if not real:
            continue
        where = scope.expression.args.get("where")
        parts = [_render(part) for part in _conjuncts(where)] if where else []
        single = len({full for full, _ in real}) == 1
        for full, _alias in real:
            for filt in by_table.get(full, []):
                aliases = {alias for name, alias in real if name == full}
                wanted = _filter_candidates(
                    sqlglot.parse_one(filt.sql, read="postgres"),
                    full,
                    aliases,
                    single,
                )
                if not wanted.intersection(parts):
                    fail(
                        REQUIRED_FILTERS,
                        f"This query uses `{full}` but leaves out a required filter: "
                        f"{filt.reason} (`{filt.sql}`).",
                    )


def _own_nodes(scope, kind) -> list:
    """Nodes of one kind in this scope's own SELECT list and HAVING."""
    expression = scope.expression
    if not isinstance(expression, exp.Select):
        return []
    found: list = []
    areas = list(expression.args.get("expressions", []))
    having = expression.args.get("having")
    if having is not None:
        areas.append(having)

    def visit(node: exp.Expression) -> None:
        if isinstance(node, exp.Select) and node is not expression:
            return
        if isinstance(node, kind):
            found.append(node)
        for child in node.iter_expressions():
            visit(child)

    for area in areas:
        visit(area)
    return found


def _rule_counting(tree: exp.Expression, fail) -> None:
    """Rule 5: COUNT over more than one table belongs in a learning run."""
    for scope in traverse_scope(tree):
        counts = _own_nodes(scope, exp.Count)
        if not counts:
            continue
        if len(_direct_real_tables(scope)) > 1:
            fail(
                COUNTING,
                "`COUNT` counts rows; counts over one table at once only make sense "
                "in a learning run.",
            )
            return


def _direct_real_tables(scope) -> list:
    """Normalized names of the real tables one SELECT reads itself."""
    if not isinstance(scope.expression, exp.Select):
        return []
    ctes = set()
    for source in scope.cte_sources:
        ctes.add(str(source).lower() if not isinstance(source, str) else source.lower())
    names = []
    for table in _direct_tables(scope):
        if isinstance(table.this, exp.Func):
            continue
        if table.name.lower() in ctes:
            continue
        full = normalize_table(f"{table.db}.{table.name}" if table.db else table.name)
        if full not in names:
            names.append(full)
    return names


def _rule_averaging(tree: exp.Expression, catalog: Catalog, fail) -> None:
    """Rule 6: AVG only over a listed pre-computed average column."""
    wanted = {name.lower() for name in catalog.average_columns}
    first = catalog.average_columns[0] if catalog.average_columns else None
    for node in tree.find_all(exp.Avg):
        arg = node.this
        names = set()
        if arg is not None:
            names.add(arg.sql(dialect="postgres").lower())
            for column in arg.find_all(exp.Column):
                names.add(column.name.lower())
        if not names.intersection(wanted):
            if first is None:
                reason = (
                    "`AVG` only makes sense over a listed average column: use one of "
                    "Charie's pre-computed averages instead."
                )
            else:
                reason = (
                    f"`AVG` only makes sense over `{first}`: use one of Charie's "
                    "pre-computed averages instead."
                )
            fail(AVERAGING, reason)


def _rule_explicit_columns(tree: exp.Expression, fail) -> None:
    """Rule: name the columns; bare `*` fails, `t.*` needs one table."""
    for scope in traverse_scope(tree):
        if not isinstance(scope.expression, exp.Select):
            continue
        real = _direct_real_tables(scope)
        for item in scope.expression.args.get("expressions", []):
            if isinstance(item, exp.Star):
                if real:
                    fail(
                        EXPLICIT_COLUMNS,
                        f"This query would read a whole `{real[0]}` row: name the "
                        "columns it needs. (Rule: explicit-columns)",
                    )
                continue
            if isinstance(item, exp.Column) and isinstance(item.this, exp.Star):
                if len(real) == 1:
                    continue
                full = None
                qualifier = (item.table or "").lower()
                for name in real:
                    if name.split(".", 1)[1] == qualifier:
                        full = name
                        break
                fail(
                    EXPLICIT_COLUMNS,
                    f"This query would read a whole `{full or real[0] if real else '?'}` row: "
                    "name the columns it needs. (Rule: explicit-columns)",
                )


def plan_rows(connector, sql: str) -> int | None:
    """The planner's own row estimate for one query, or None when unclear."""
    import re

    result = connector.run_query("EXPLAIN " + sql)
    text = "\n".join(str(cell) for row in result.rows for cell in row)
    match = re.search(r"rows=(\d+)", text)
    return int(match.group(1)) if match else None


def explain_plan(sql: str, catalog: Catalog, connector, max_rows: int = 50_000) -> str | None:
    """The database's own row estimate, or None when it agrees the plan is cheap.

    Never runs a blocked query: the checker goes first.
    """
    report = check_sql(sql, catalog, max_rows=max_rows)
    if not report.ok:
        return None
    rows = plan_rows(connector, report.sql)
    if rows is None or rows < max_rows:
        return None
    return (
        f"Postgres thinks this query reads about {rows} rows, over the {max_rows} row "
        "limit. Narrow it down: add a filter, a GROUP BY, or a smaller LIMIT."
    )


def _apply_limit(top: exp.Select, max_rows: int) -> None:
    """No GROUP BY and no (good) LIMIT: add `LIMIT max_rows + 1`."""
    if top.args.get("group") is not None:
        return
    wanted = max_rows + 1
    limit = top.args.get("limit")
    if limit is not None:
        current = limit.expression
        if (
            isinstance(current, exp.Literal)
            and not current.is_string
            and int(current.name) <= wanted
        ):
            return
        limit.set("expression", exp.Literal.number(wanted))
        return
    top.set("limit", exp.Limit(expression=exp.Literal.number(wanted)))
