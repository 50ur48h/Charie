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
DOUBLE_COUNTING = "double_counting"
AVERAGE_OF_AVERAGES = "average_of_averages"
TOO_HEAVY = "too_heavy"

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


def check_sql(
    sql: str,
    catalog: Catalog,
    *,
    max_rows: int = 50_000,
    explain=None,
    max_plan_cost: int = 5_000_000,
) -> CheckReport:
    """Check one query against the catalog; collect every failure.

    `explain`, when given, plans the query as written last, only when rules
    1-6 passed (before the row cap is added, which would make any plan look
    cheap). It takes that SQL and returns the parsed `EXPLAIN (FORMAT JSON)`
    result.
    """
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
        _rule_double_counting(tree, catalog, fail)
        _rule_average_of_averages(tree, catalog, fail)
        _rule_derived_tables(tree, catalog, fail)

    if len(trees) == 1 and isinstance(trees[0], exp.Select):
        # Rule 7 judges the query as written: the row cap below would make any
        # plan look cheap, so the cost check plans the query before the cap.
        uncut = trees[0].sql(dialect="postgres")
        _apply_limit(trees[0], max_rows)
        rendered = trees[0].sql(dialect="postgres")
    else:
        uncut = rendered = sql
    if not reasons and explain is not None:
        _rule_too_heavy(uncut, explain, max_plan_cost, fail)
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
    # sqlglot reads CALL, DO and LOCK as plain commands: read the first word.
    for command in tree.find_all(exp.Command):
        words = command.sql(dialect="postgres").strip().split()
        word = words[0].upper().rstrip(";") if words else ""
        if word in ("CALL", "DO", "LOCK") and word not in whats:
            whats.append(word)
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


def is_dangerous_function(name: str) -> bool:
    """True when rule 3 would refuse this function name as dangerous."""
    upper = name.strip().upper()
    return upper in _DANGEROUS_EXACT or upper.startswith(_DANGEROUS_PREFIX)


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


def _own_nodes(scope, kinds) -> list:
    """Nodes of these kinds in this scope's own SELECT list and HAVING."""
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
        if isinstance(node, kinds):
            found.append(node)
        for child in node.iter_expressions():
            visit(child)

    for area in areas:
        visit(area)
    return found


def _reachable_many(start: str, catalog: Catalog) -> set[str]:
    """Tables reached from `start` by following one-to-many links (1+ steps)."""
    seen: set[str] = set()
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for link in catalog.links:
            if link.one_table == current and link.many_table not in seen:
                seen.add(link.many_table)
                frontier.append(link.many_table)
    return seen


def _agg_column_table(agg: exp.Expression, tables: list[tuple[str, str]]) -> tuple | None:
    """`(table, column)` the aggregate reads, or None when it stays unclear."""
    arg = agg.this
    if isinstance(agg, exp.Count) and (arg is None or isinstance(arg, (exp.Star, exp.Distinct))):
        return None
    columns = list(arg.find_all(exp.Column)) if arg is not None else []
    if not columns:
        return None
    by_alias = {alias: full for full, alias in tables}
    by_name = {full.split(".", 1)[1]: full for full, _ in tables}
    found: set[str] = set()
    for column in columns:
        qualifier = (column.table or "").lower()
        if qualifier:
            table = by_alias.get(qualifier, by_name.get(qualifier))
            if table is None:
                return None
            found.add(table)
        elif len({full for full, _ in tables}) == 1:
            found.add(tables[0][0])
        else:
            return None
    if len(found) != 1:
        return None
    return (next(iter(found)), columns[0].name.lower())


def _rule_double_counting(tree: exp.Expression, catalog: Catalog, fail) -> None:
    """Rule 5: no adding up A after joining a table A fans out to."""
    if not catalog.links:
        return
    for scope in traverse_scope(tree):
        if not isinstance(scope.expression, exp.Select):
            continue
        tables = _scope_real_tables(scope)
        if len({full for full, _ in tables}) < 2:
            continue
        for agg in _own_nodes(scope, (exp.Sum, exp.Avg, exp.Count)):
            found = _agg_column_table(agg, tables)
            if found is None:
                continue
            table, column = found
            for full in sorted(_reachable_many(table, catalog)):
                if any(full == other for other, _ in tables):
                    fail(
                        DOUBLE_COUNTING,
                        f"This query adds up `{table}.{column}` after joining `{full}`, "
                        f"which has many rows for each `{table}` row. Each `{table}` row "
                        f"would be counted once per `{full}` row. Add up `{full}` first "
                        "in a sub-query, or don't join it.",
                    )
                    break


def _scope_real_tables(scope) -> list[tuple[str, str]]:
    """`(table, alias)` pairs one SELECT reads itself (no CTEs, no functions)."""
    if not isinstance(scope.expression, exp.Select):
        return []
    ctes = set()
    for source in scope.cte_sources:
        ctes.add(str(source).lower() if not isinstance(source, str) else source.lower())
    pairs: list[tuple[str, str]] = []
    for table in _direct_tables(scope):
        if isinstance(table.this, exp.Func):
            continue
        if table.name.lower() in ctes:
            continue
        full = normalize_table(f"{table.db}.{table.name}" if table.db else table.name)
        alias = (table.alias or table.name).lower()
        if (full, alias) not in pairs:
            pairs.append((full, alias))
    return pairs


def _avg_made_outputs(tree: exp.Expression) -> dict[str, set[str]]:
    """Source name to the output columns a sub-query or WITH part made by AVG."""
    made: dict[str, set[str]] = {}

    def record(query: exp.Expression, name: str) -> None:
        if not name or not isinstance(query, exp.Select):
            return
        for item in query.args.get("expressions", []):
            inner = item
            out = None
            if isinstance(item, exp.Alias):
                out = item.alias.lower()
                inner = item.this
            elif isinstance(item, exp.Column):
                out = item.name.lower()
            if out and inner.find(exp.Avg) is not None:
                made.setdefault(name, set()).add(out)

    for cte in tree.find_all(exp.CTE):
        record(cte.this, str(cte.alias or "").lower())
    for sub in tree.find_all(exp.Subquery):
        alias = sub.args.get("alias")
        raw = alias.sql(dialect="postgres") if alias is not None else ""
        record(sub.this, raw.split("(")[0].strip().strip('"').lower())
    return made


def _enclosing_sources(node: exp.Expression, tree: exp.Expression) -> set[str]:
    """Source names the AVG's own SELECT reads, plus every WITH name in scope."""
    select = node
    while select is not None and not isinstance(select, exp.Select):
        select = select.parent
    names: set[str] = set()
    if isinstance(select, exp.Select):
        from_ = select.args.get("from_")
        items = []
        if from_ is not None:
            items.append(from_.this)
            items.extend(from_.args.get("expressions", []))
        for join in select.args.get("joins", []):
            items.append(join.this)
        for item in items:
            if isinstance(item, exp.Table) and not isinstance(item.this, exp.Func):
                names.add((item.alias or item.name).lower())
            elif isinstance(item, exp.Subquery):
                alias = item.args.get("alias")
                if alias is not None:
                    names.add(alias.sql(dialect="postgres").split("(")[0].strip().lower())
    for cte in tree.find_all(exp.CTE):
        names.add(str(cte.alias or "").lower())
    return names


def _rule_average_of_averages(tree: exp.Expression, catalog: Catalog, fail) -> None:
    """Rule 6: no AVG over numbers that are already averages."""
    made = _avg_made_outputs(tree)
    wanted = {name.lower() for name in catalog.average_columns}
    for node in tree.find_all(exp.Avg):
        arg = node.this
        if arg is None:
            continue
        for column in arg.find_all(exp.Column):
            name = column.name.lower()
            shown = column.sql(dialect="postgres")
            if name in wanted:
                blocked = True
            else:
                qualifier = (column.table or "").lower()
                sources = {qualifier} if qualifier else _enclosing_sources(node, tree)
                blocked = any(name in made.get(source, set()) for source in sources if source)
            if blocked:
                fail(
                    AVERAGE_OF_AVERAGES,
                    f"This query averages numbers that are already averages (`{shown}`). "
                    "Work out the average as total ÷ count instead.",
                )


def _derived_sources(scope) -> dict[str, exp.Select]:
    """Alias to inner SELECT for each derived table this scope reads."""
    if not isinstance(scope.expression, exp.Select):
        return {}
    from_ = scope.expression.args.get("from_")
    items = []
    if from_ is not None:
        items.append(from_.this)
        items.extend(from_.args.get("expressions", []))
    for join in scope.expression.args.get("joins", []):
        items.append(join.this)
    found: dict[str, exp.Select] = {}
    for item in items:
        if isinstance(item, exp.Subquery) and isinstance(item.this, exp.Select):
            alias = item.args.get("alias")
            if alias is None:
                continue
            name = alias.sql(dialect="postgres").split("(")[0].strip().strip('"').lower()
            if name:
                found[name] = item.this
    return found


def _derived_keys(inner: exp.Select) -> set[str]:
    """Output columns a scope may join on: grouped keys, or every column."""
    names: dict[str, str] = {}
    for item in inner.args.get("expressions", []):
        if isinstance(item, exp.Alias):
            names[_render(item.this)] = item.alias.lower()
        elif isinstance(item, exp.Column):
            names[_render(item)] = item.name.lower()
    group = inner.args.get("group")
    if group is None:
        if inner.args.get("distinct") is None:
            return set()
        return set(names.values())
    wanted = {_render(part) for part in group.expressions}
    return {name for render, name in names.items() if render in wanted}


def _join_parts(condition: exp.Expression) -> list:
    """The top-level AND parts of a JOIN condition."""
    parts: list = []
    stack = [_unwrap(condition)]
    while stack:
        node = _unwrap(stack.pop())
        if isinstance(node, exp.And):
            stack.append(node.left)
            stack.append(node.right)
        else:
            parts.append(node)
    return parts


def _rule_derived_tables(tree: exp.Expression, catalog: Catalog, fail) -> None:
    """Rule 5b: joins of derived tables stay on grouped keys; no re-adding.

    Each derived table the builder emits is grouped (or distinct) at a
    proven grain. A join to one is safe only on its key columns, and an
    outer aggregate over joined sources would count rows twice.
    """
    del catalog
    for scope in traverse_scope(tree):
        if not isinstance(scope.expression, exp.Select):
            continue
        sources = _derived_sources(scope)
        if not sources:
            continue
        keys = {name: _derived_keys(inner) for name, inner in sources.items()}
        real = [full for full, _ in _scope_real_tables(scope)]
        aggregations = _own_nodes(scope, (exp.Sum, exp.Avg, exp.Count))
        if aggregations and len(sources) + len(real) > 1:
            fail(
                DOUBLE_COUNTING,
                "This query adds up numbers after joining, so joined rows "
                "would count twice. Add each side up in a sub-query first.",
            )
            continue
        if aggregations and len(sources) == 1 and not real:
            name = next(iter(sources))
            inner = sources[name]
            if inner.args.get("group") is None and inner.args.get("distinct") is None:
                fail(
                    DOUBLE_COUNTING,
                    "This query adds up a sub-query with no grouping, so its "
                    "grain is unproven. Group the sub-query first.",
                )
                continue
            columns: list[str] = []
            for node in aggregations:
                arg = node.this
                if arg is not None:
                    columns.extend(col for col in arg.find_all(exp.Column))
            if any(col.name.lower() not in keys[name] for col in columns):
                fail(
                    DOUBLE_COUNTING,
                    "This query adds up a sub-query column that isn't grouped, "
                    "so joined rows would count twice.",
                )
                continue
        for join in scope.expression.args.get("joins", []):
            condition = join.args.get("on")
            if condition is None:
                continue
            for part in _join_parts(condition):
                if not isinstance(part, exp.Binary):
                    cols = [
                        node
                        for node in part.find_all(exp.Column)
                        if (node.table or "").lower() in keys
                    ]
                    if cols:
                        fail(
                            DOUBLE_COUNTING,
                            "This query joins a sub-query on something that isn't "
                            "an equality, so the grain is unproven.",
                        )
                        break
                    continue
                touched = any(
                    (node.table or "").lower() in keys
                    for node in (part.left, part.right)
                    if isinstance(node, exp.Column)
                )
                if not touched:
                    continue
                if not isinstance(part, (exp.EQ, exp.NullSafeEQ)):
                    fail(
                        DOUBLE_COUNTING,
                        "This query joins a sub-query on something that isn't "
                        "an equality, so the grain is unproven.",
                    )
                    break
                left, right = part.left, part.right
                if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
                    fail(
                        DOUBLE_COUNTING,
                        "This query joins a sub-query on something that isn't "
                        "two columns, so the grain is unproven.",
                    )
                    break
                bad = False
                for column in (left, right):
                    qualifier = (column.table or "").lower()
                    if qualifier in keys and column.name.lower() not in keys[qualifier]:
                        bad = True
                if bad:
                    fail(
                        DOUBLE_COUNTING,
                        "This query joins a sub-query on columns that aren't "
                        "grouped, so rows would count twice.",
                    )
                    break


def _rule_too_heavy(sql: str, explain, max_plan_cost: int, fail) -> None:
    """Rule 7: the plan's Total Cost stays under the limit (EXPLAIN never runs)."""
    try:
        result = explain(sql)
    except Exception as err:  # noqa: BLE001
        message = str(err).split("\n")[0].strip()
        fail(TOO_HEAVY, f"Charie couldn't estimate this query: `{message}`.")
        return
    try:
        cost = result[0]["Plan"]["Total Cost"]
    except (KeyError, IndexError, TypeError):
        fail(TOO_HEAVY, "Charie couldn't estimate this query: `the plan can't be read`.")
        return
    if cost > max_plan_cost:
        fail(
            TOO_HEAVY,
            "This query looks too heavy to run safely (Postgres estimates a cost "
            f"of `{cost}`; the limit is `{max_plan_cost}`). Try a shorter period "
            "or fewer details.",
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
