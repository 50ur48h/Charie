"""The SQL policy engine (architecture Part 7.1 diagram 6, 7.5)."""

# sqlglot 30 turned `expressions` into a package that re-exports its node classes without an...
# pyright: reportPrivateImportUsage=false

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from typing import TypeGuard, cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError, SqlglotError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope
from sqlglot.schema import MappingSchema
from sqlglot.tokens import TokenType

from charie.catalog.browse import Catalog, CatalogTableView
from charie.connectors.base import PolicyGrant, ValidatedQuery
from charie.dal.errors import PolicyViolation, ViolationCode
from charie.dal.policy import SourcePolicy

__all__ = [
    "ColumnRef",
    "Projection",
    "TableRef",
    "Validated",
    "date_literals",
    "filtered_columns",
    "literals_in",
    "tables_named",
    "validate",
]

#: This module is on ``SANCTIONED_VALIDATORS`` (connectors/base.py).
_GRANT = PolicyGrant(__name__)

POLICY_DENY = "deny"
POLICY_MASK = "mask"

#: Ceilings on the statement, not on SQL.
MAX_SQL_LENGTH = 20_000
MAX_NESTING_DEPTH = 50

#: Schemas the engine keeps for itself.
_SYSTEM_SCHEMAS = frozenset({"information_schema", "sys", "sysibm", "mysql", "performance_schema"})
_SYSTEM_SCHEMA_PREFIXES = ("pg_",)

#: Named only to refuse them better.
_DENIED_FUNCTIONS = frozenset(
    {
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "pg_sleep",
        "pg_terminate_backend",
        "pg_reload_conf",
        "lo_import",
        "lo_export",
        "dblink",
        "dblink_exec",
        "query_to_xml",
        "openrowset",
        "opendatasource",
        "openquery",
        "openxml",
        "xp_cmdshell",
        "xp_dirtree",
        "xp_fileexist",
        "sp_executesql",
        "sp_oacreate",
        "sp_oamethod",
        "fn_get_audit_file",
        "waitfor",
    }
)
_DENIED_FUNCTION_PREFIXES = ("xp_", "sp_", "pg_", "lo_")

#: Functions sqlglot cannot type that are nonetheless allowed.
_ALLOWED_UNTYPED_FUNCTIONS: frozenset[str] = frozenset()

#: Node classes that must not appear anywhere in the tree.
_FORBIDDEN_NODES: tuple[type, ...] = (
    exp.DML,
    exp.DDL,
    exp.Alter,
    exp.Analyze,
    exp.Command,
    exp.Commit,
    exp.Copy,
    exp.Drop,
    exp.Execute,
    exp.Grant,
    exp.Into,
    exp.Lock,
    exp.ReadCSV,
    exp.Refresh,
    exp.Rollback,
    exp.Set,
    exp.Transaction,
    exp.TruncateTable,
    exp.Use,
)

#: What a forbidden node is called when refusing it. sqlglot's class names are close enough to...
_OPERATION_NAMES: dict[type, str] = {
    exp.Command: "this statement",
    exp.Into: "SELECT INTO",
    exp.Lock: "a locking clause",
    exp.ReadCSV: "reading a file",
    exp.Set: "SET",
    exp.Transaction: "transaction control",
    exp.TruncateTable: "TRUNCATE",
}


@dataclass(frozen=True, slots=True)
class TableRef:
    """A table, as the catalog spells it."""

    schema: str
    table: str

    def __str__(self) -> str:
        return f"{self.schema}.{self.table}"


@dataclass(frozen=True, slots=True)
class ColumnRef:
    schema: str
    table: str
    column: str

    def __str__(self) -> str:
        return f"{self.schema}.{self.table}.{self.column}"


@dataclass(frozen=True, slots=True)
class Projection:
    """One column of the result, and where its value comes from."""

    #: The name the engine will return for this column.
    name: str
    #: The catalog column, when the projection is one.
    source: ColumnRef | None
    #: True when a masked column's value can be read out of this cell.
    sensitive: bool


@dataclass(frozen=True, slots=True)
class Validated:
    """SQL that may run, and what it will touch."""

    query: ValidatedQuery
    tables: tuple[TableRef, ...]
    columns: tuple[ColumnRef, ...]
    masked: tuple[ColumnRef, ...]
    projections: tuple[Projection, ...] = ()
    #: The row cap written into the SQL, when one was asked for.
    row_limit: int | None = None

    @property
    def sql(self) -> str:
        return self.query.sql

    @property
    def touches_sensitive(self) -> bool:
        return bool(self.masked)


def validate(sql: str, *, source: SourcePolicy, max_rows: int | None = None) -> Validated:
    """Judge one statement against one data source."""
    try:
        return _validate(sql, source=source, max_rows=max_rows)
    except RecursionError:
        failure = PolicyViolation(
            ViolationCode.TOO_COMPLEX,
            "This query nests too deeply to be checked. Simplify it, or split it into steps.",
        )
    raise failure


def _validate(sql: str, *, source: SourcePolicy, max_rows: int | None) -> Validated:
    dialect = source.dialect
    statement, is_explain = _parse_one_read_only(sql, dialect)

    _reject_forbidden_nodes(statement)
    _reject_unvouched_functions(statement)

    tables = _bind_tables(statement, source.catalog)
    qualified = _resolve_identifiers(statement, source, tables)
    columns, masked, origin = _apply_column_policy(qualified, source.catalog)
    projections = _projections(qualified, origin, masked)

    # Last, so the limit lands on the statement that passed every rule rather than on one still...
    row_limit = None if is_explain else _bound_rows(qualified, max_rows)

    canonical = qualified.sql(dialect=dialect, comments=False)
    if is_explain:
        canonical = f"EXPLAIN {canonical}"

    return Validated(
        query=ValidatedQuery(_GRANT, sql=canonical, dialect=dialect),
        tables=tuple(sorted(set(tables.values()), key=str)),
        columns=tuple(sorted(columns, key=str)),
        masked=tuple(sorted(masked, key=str)),
        projections=projections,
        row_limit=row_limit,
    )


# --- 1-2 ---


def _parse_one_read_only(sql: str, dialect: str) -> tuple[exp.Expression, bool]:
    """Parse in the source's own dialect and return the single read statement."""
    # The refusal is built inside the handler and raised outside it.
    _refuse_if_too_complex(sql, dialect)

    failure: PolicyViolation | None = None
    parsed: list[exp.Expression] = []
    try:
        parsed = [
            statement
            for statement in sqlglot.parse(sql, dialect=dialect)
            if isinstance(statement, exp.Expression)
        ]
    except ParseError as error:
        failure = PolicyViolation(
            ViolationCode.PARSE_ERROR,
            f"This is not valid {dialect} SQL{_where(error)}. Rewrite the query.",
        )
    except SqlglotError:
        # Depth limits and tokenizer failures.
        failure = PolicyViolation(
            ViolationCode.PARSE_ERROR, f"This could not be read as {dialect} SQL."
        )
    if failure is not None:
        raise failure

    if not parsed:
        raise PolicyViolation(ViolationCode.EMPTY_STATEMENT, "There is no statement here to run.")
    if len(parsed) > 1:
        raise PolicyViolation(
            ViolationCode.MULTIPLE_STATEMENTS,
            f"Send one statement. This is {len(parsed)}; only the first would be considered.",
        )

    statement = parsed[0]
    if _is_explain(statement):
        try:
            inner, nested = _parse_one_read_only(_explain_body(statement), dialect)
        except PolicyViolation as violation:
            # A body that does not parse means the EXPLAIN is malformed, and "line 1.
            if violation.code is not ViolationCode.PARSE_ERROR:
                raise
            explain_failure = PolicyViolation(
                ViolationCode.STATEMENT_NOT_READ_ONLY,
                "EXPLAIN must be followed by a plain SELECT — no ANALYZE, and no options.",
            )
            raise explain_failure from None
        if nested:
            raise PolicyViolation(
                ViolationCode.STATEMENT_NOT_READ_ONLY, "EXPLAIN cannot explain an EXPLAIN."
            )
        return inner, True

    if not isinstance(statement, exp.Select | exp.SetOperation):
        raise PolicyViolation(
            ViolationCode.STATEMENT_NOT_READ_ONLY,
            "Only SELECT is permitted here (optionally under EXPLAIN). "
            f"This is {_operation_name(statement)}.",
        )
    return statement, False


def tables_named(sql: str, *, dialect: str) -> tuple[str, ...]:
    """The tables a statement mentions, without validating or running anything."""
    with suppress(PolicyViolation, RecursionError, SqlglotError):
        _refuse_if_too_complex(sql, dialect)
        parsed = sqlglot.parse_one(sql, read=dialect)
        # A CTE name parses as a table and is not one.
        defined = {
            cte.alias_or_name.lower() for cte in parsed.find_all(exp.CTE) if cte.alias_or_name
        }
        found = {
            table.name.lower()
            for table in parsed.find_all(exp.Table)
            if table.name and table.name.lower() not in defined
        }
        return tuple(sorted(found))
    return ()


def filtered_columns(sql: str, *, dialect: str) -> frozenset[str]:
    """Columns this statement constrains, lowercased and unqualified."""
    with suppress(PolicyViolation, RecursionError, SqlglotError):
        _refuse_if_too_complex(sql, dialect)
        parsed = sqlglot.parse_one(sql, read=dialect)
        found: set[str] = set()
        for predicate in (
            *parsed.find_all(exp.Where),
            *parsed.find_all(exp.Having),
            *parsed.find_all(exp.Join),
            # A qualifying predicate can also sit in a window's `QUALIFY`.
            *parsed.find_all(exp.Qualify),
        ):
            found |= {
                column.name.lower() for column in predicate.find_all(exp.Column) if column.name
            }
        return frozenset(found)
    return frozenset()


def literals_in(sql: str, *, dialect: str) -> frozenset[str]:
    """Every literal the statement contains, as text."""
    with suppress(PolicyViolation, RecursionError, SqlglotError):
        _refuse_if_too_complex(sql, dialect)
        parsed = sqlglot.parse_one(sql, read=dialect)
        return frozenset(str(item.this).lower() for item in parsed.find_all(exp.Literal))
    return frozenset()


#: A bare ISO date.
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def date_literals(sql: str, *, dialect: str) -> tuple[str, ...]:
    """Every date written into a statement, as ``YYYY-MM-DD`` strings."""
    with suppress(PolicyViolation, RecursionError, SqlglotError):
        _refuse_if_too_complex(sql, dialect)
        parsed = sqlglot.parse_one(sql, read=dialect)
        found = {
            node.this
            for node in parsed.find_all(exp.Literal)
            if node.is_string and _ISO_DATE.fullmatch(str(node.this))
        }
        return tuple(sorted(found))
    return ()


def _refuse_if_too_complex(sql: str, dialect: str) -> None:
    """Refuse what is too big or too deep to inspect, before inspecting it."""
    if len(sql) > MAX_SQL_LENGTH:
        raise PolicyViolation(
            ViolationCode.TOO_COMPLEX,
            f"This statement is longer than the {MAX_SQL_LENGTH:,}-character limit. "
            "Ask for less in one query.",
        )

    depth = deepest = 0
    try:
        for token in sqlglot.tokenize(sql, read=dialect):
            if token.token_type is TokenType.L_PAREN:
                depth += 1
                deepest = max(deepest, depth)
            elif token.token_type is TokenType.R_PAREN:
                depth -= 1
    except SqlglotError:
        # Not tokenizable at all. The parser is about to say so more precisely.
        return

    if deepest > MAX_NESTING_DEPTH:
        raise PolicyViolation(
            ViolationCode.TOO_COMPLEX,
            f"This query nests {deepest} levels deep, past the limit of "
            f"{MAX_NESTING_DEPTH}. Simplify it, or split it into steps.",
        )


def _is_explain(statement: exp.Expression) -> TypeGuard[exp.Command]:
    return (
        isinstance(statement, exp.Command)
        and isinstance(statement.this, str)
        and statement.this.strip().upper() == "EXPLAIN"
    )


def _explain_body(statement: exp.Command) -> str:
    body = statement.args.get("expression")
    if isinstance(body, exp.Literal) and isinstance(body.this, str):
        return body.this
    raise PolicyViolation(
        ViolationCode.STATEMENT_NOT_READ_ONLY, "EXPLAIN needs a SELECT statement after it."
    )


def _where(error: ParseError) -> str:
    """The position of a parse failure, and nothing else from it."""
    for item in error.errors:
        line, column = item.get("line"), item.get("col")
        if isinstance(line, int) and isinstance(column, int):
            return f" (line {line}, column {column})"
    return ""


def _operation_name(node: exp.Expr) -> str:
    for kind, name in _OPERATION_NAMES.items():
        if isinstance(node, kind):
            return name
    return type(node).__name__.upper()


# --- Nothing that writes, anywhere ---


def _reject_forbidden_nodes(statement: exp.Expression) -> None:
    """Walk the whole tree, not just the top of it."""
    for node in statement.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise PolicyViolation(
                ViolationCode.WRITE_OPERATION,
                f"{_operation_name(node)} is not permitted: this connection reads and "
                "nothing else. Rewrite the query as a SELECT.",
                subject=_operation_name(node),
            )


# --- 4-5 ---


def _reject_unvouched_functions(statement: exp.Expression) -> None:
    for node in statement.find_all(exp.Anonymous):
        name = node.name.lower()
        if name in _ALLOWED_UNTYPED_FUNCTIONS:
            continue
        if name in _DENIED_FUNCTIONS or name.startswith(_DENIED_FUNCTION_PREFIXES):
            raise PolicyViolation(
                ViolationCode.DENIED_FUNCTION,
                f"The function {node.name} is not permitted.",
                subject=node.name,
            )
        raise PolicyViolation(
            ViolationCode.UNKNOWN_FUNCTION,
            f"The function {node.name} is not one this service can vouch for. "
            "Use standard SQL functions, or aggregate in the query and shape the "
            "result afterwards.",
            subject=node.name,
        )


# --- Every table is one the catalog knows ---


def _bind_tables(statement: exp.Expression, catalog: Catalog) -> dict[str, TableRef]:
    """Resolve every table reference, and rewrite it to the catalog's spelling."""
    by_qualified, by_name = _catalog_index(catalog)
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    bound: dict[str, TableRef] = {}

    for node in statement.find_all(exp.Table):
        if not isinstance(node.this, exp.Identifier):
            # FROM generate_series(...) and friends: a function standing where a table belongs.
            raise PolicyViolation(
                ViolationCode.TABLE_FUNCTION,
                "Only catalogued tables and views may be read, not table functions.",
            )
        if node.catalog:
            raise PolicyViolation(
                ViolationCode.CROSS_DATABASE,
                f"{node.catalog}.{node.db}.{node.name} names another database. "
                "This data source reads one database only.",
                subject=node.catalog,
            )

        name, schema = node.name, node.db
        # A bare name may be a CTE defined in this same statement.
        if not schema and name.lower() in cte_names:
            continue

        if schema and _is_system_schema(schema):
            raise PolicyViolation(
                ViolationCode.SYSTEM_SCHEMA,
                f"{schema} is the database's own dictionary and is not readable here. "
                "Structure comes from the catalog, which you already have.",
                subject=schema,
            )

        ref = _lookup_table(schema, name, by_qualified, by_name)
        node.set("this", exp.to_identifier(ref.table, quoted=True))
        node.set("db", exp.to_identifier(ref.schema, quoted=True))
        bound[str(ref)] = ref

    if not bound:
        raise PolicyViolation(
            ViolationCode.UNKNOWN_TABLE,
            "This query reads no catalogued table. Name a table from the catalog.",
        )
    return bound


def _catalog_index(
    catalog: Catalog,
) -> tuple[dict[tuple[str, str], CatalogTableView], dict[str, list[CatalogTableView]]]:
    """Two lookups over the active snapshot, both case-folded."""
    by_qualified: dict[tuple[str, str], CatalogTableView] = {}
    by_name: dict[str, list[CatalogTableView]] = {}
    for table in catalog.tables:
        by_qualified[(table.schema_name.lower(), table.table_name.lower())] = table
        by_name.setdefault(table.table_name.lower(), []).append(table)
    return by_qualified, by_name


def _lookup_table(
    schema: str,
    name: str,
    by_qualified: dict[tuple[str, str], CatalogTableView],
    by_name: dict[str, list[CatalogTableView]],
) -> TableRef:
    if schema:
        found = by_qualified.get((schema.lower(), name.lower()))
        if found is None:
            raise PolicyViolation(
                ViolationCode.UNKNOWN_TABLE,
                f"There is no table {schema}.{name} in this data source's catalog.",
                subject=f"{schema}.{name}",
            )
        return TableRef(found.schema_name, found.table_name)

    candidates = by_name.get(name.lower(), [])
    if not candidates:
        raise PolicyViolation(
            ViolationCode.UNKNOWN_TABLE,
            f"There is no table named {name} in this data source's catalog.",
            subject=name,
        )
    if len(candidates) > 1:
        schemas = ", ".join(sorted(table.schema_name for table in candidates))
        raise PolicyViolation(
            ViolationCode.AMBIGUOUS_TABLE,
            f"{name} exists in more than one schema ({schemas}). Qualify it.",
            subject=name,
        )
    return TableRef(candidates[0].schema_name, candidates[0].table_name)


def _is_quoted(column: exp.Column) -> bool:
    identifier = column.this
    return isinstance(identifier, exp.Identifier) and bool(identifier.quoted)


def _is_system_schema(schema: str) -> bool:
    folded = schema.lower()
    return folded in _SYSTEM_SCHEMAS or folded.startswith(_SYSTEM_SCHEMA_PREFIXES)


# --- Stars expanded, columns qualified — against the catalog, before any rule ---


def _resolve_identifiers(
    statement: exp.Expression, source: SourcePolicy, tables: dict[str, TableRef]
) -> exp.Expression:
    """Expand ``SELECT *`` and attach every column to the table it came from."""
    schema = _sqlglot_schema(source.catalog, tables, source.dialect)
    qualified: exp.Expression | None = None
    try:
        qualified = qualify(
            statement,
            dialect=source.dialect,
            schema=schema,
            infer_schema=False,
            validate_qualify_columns=True,
        )
    except OptimizeError:
        # Diagnosed and raised outside the handler, so the optimizer's own message.
        qualified = None
    if qualified is None:
        raise _diagnose(statement, source.catalog, tables)
    return qualified


def _sqlglot_schema(catalog: Catalog, tables: dict[str, TableRef], dialect: str) -> MappingSchema:
    """The catalog, in the shape the qualifier reads, holding only what is used."""
    wanted = {(ref.schema, ref.table) for ref in tables.values()}
    schema: dict[str, dict[str, dict[str, str]]] = {}
    for table in catalog.tables:
        if (table.schema_name, table.table_name) not in wanted:
            continue
        schema.setdefault(table.schema_name, {})[table.table_name] = {
            column.name: column.data_type for column in table.columns
        }
    # cast: MappingSchema declares `dict[str, object]`, and a dict is invariant in its value type.
    return MappingSchema(cast("dict[str, object]", schema), dialect=dialect)


def _diagnose(
    statement: exp.Expression, catalog: Catalog, tables: dict[str, TableRef]
) -> PolicyViolation:
    """Say which column failed, and why, in the agent's terms."""
    used = set(tables.values())
    available: dict[str, set[str]] = {}
    exact_available: dict[str, set[str]] = {}
    columns_of: dict[TableRef, set[str]] = {}
    exact_columns_of: dict[TableRef, set[str]] = {}
    for table in catalog.tables:
        ref = TableRef(table.schema_name, table.table_name)
        if ref not in used:
            continue
        columns_of[ref] = {column.name.lower() for column in table.columns}
        exact_columns_of[ref] = {column.name for column in table.columns}
        for column in table.columns:
            available.setdefault(column.name.lower(), set()).add(table.table_name)
            exact_available.setdefault(column.name, set()).add(table.table_name)

    aliases: dict[str, TableRef] = {}
    for node in statement.find_all(exp.Table):
        if isinstance(node.this, exp.Identifier):
            aliases[node.alias_or_name.lower()] = TableRef(node.db, node.name)

    for column in statement.find_all(exp.Column):
        # A quoted identifier means what it says, case included.
        exact = _is_quoted(column)
        wanted = column.name if exact else column.name.lower()
        if column.table:
            owner = aliases.get(column.table.lower())
            if owner is None or owner not in columns_of:
                # An alias belonging to a CTE or a derived table.
                continue
            known = columns_of[owner] if not exact else exact_columns_of.get(owner, set())
            if wanted not in known:
                return PolicyViolation(
                    ViolationCode.UNKNOWN_COLUMN,
                    f"There is no column {column.name} on {owner}.",
                    subject=f"{owner}.{column.name}",
                )
            continue
        owners = (exact_available if exact else available).get(wanted, set())
        if not owners:
            return PolicyViolation(
                ViolationCode.UNKNOWN_COLUMN,
                f"There is no column {column.name} on the tables this query reads.",
                subject=column.name,
            )
        if len(owners) > 1:
            return PolicyViolation(
                ViolationCode.AMBIGUOUS_COLUMN,
                f"{column.name} exists on more than one of these tables "
                f"({', '.join(sorted(owners))}). Qualify it with a table name.",
                subject=column.name,
            )

    return PolicyViolation(
        ViolationCode.UNRESOLVABLE,
        "This query could not be resolved against the catalog. Name each table "
        "and column explicitly.",
    )


# --- What each column is allowed to be used for — anywhere it appears ---


def _apply_column_policy(
    qualified: exp.Expression, catalog: Catalog
) -> tuple[set[ColumnRef], set[ColumnRef], dict[int, ColumnRef]]:
    """Check every column reference in every scope against its policy."""
    policies = _policy_index(catalog)
    touched: set[ColumnRef] = set()
    masked: set[ColumnRef] = set()
    origin: dict[int, ColumnRef] = {}

    for scope in traverse_scope(qualified):
        for column in scope.columns:
            source = scope.sources.get(column.table)
            if not isinstance(source, exp.Table):
                # A CTE or a derived table. Its own scope is in this same walk.
                continue

            ref = ColumnRef(source.db, source.name, column.name)
            decision = policies.get(_key(ref))
            if decision is None:
                raise PolicyViolation(
                    ViolationCode.UNKNOWN_COLUMN,
                    f"There is no column {column.name} on {source.db}.{source.name}.",
                    subject=str(ref),
                )
            if decision == POLICY_DENY:
                raise PolicyViolation(
                    ViolationCode.DENIED_COLUMN,
                    f"{ref} may not be queried — not in the result, and not in a "
                    "condition either. Remove it from the query.",
                    subject=str(ref),
                )
            touched.add(ref)
            origin[id(column)] = ref
            if decision == POLICY_MASK:
                masked.add(ref)

    return touched, masked, origin


# --- What the result will look like, and what may be read out of each cell ---

#: Aggregates whose result is a count or a total rather than a member of the column.
_VALUE_DESTROYING_AGGREGATES: tuple[type, ...] = (
    exp.Count,
    exp.Sum,
    exp.Avg,
    exp.Stddev,
    exp.StddevPop,
    exp.StddevSamp,
    exp.Variance,
    exp.VariancePop,
    exp.ApproxDistinct,
)


def _projections(
    qualified: exp.Expression, origin: dict[int, ColumnRef], masked: set[ColumnRef]
) -> tuple[Projection, ...]:
    """Describe the result, one entry per column the engine will return."""
    arms = [arm for arm in _select_arms(qualified) if isinstance(arm, exp.Select)]
    if not arms:
        return ()

    described: list[Projection] = []
    for index, expression in enumerate(arms[0].selects):
        peers = [arm.selects[index] for arm in arms if index < len(arm.selects)]
        source = _projected_column(expression, origin)
        described.append(
            Projection(
                name=expression.alias_or_name,
                source=source,
                sensitive=any(_carries_masked_value(peer, origin, masked) for peer in peers),
            )
        )
    return tuple(described)


def _select_arms(expression: exp.Expr) -> list[exp.Expr]:
    if isinstance(expression, exp.SetOperation):
        return _select_arms(expression.left) + _select_arms(expression.right)
    if isinstance(expression, exp.Subquery):
        return _select_arms(expression.this)
    return [expression]


def _projected_column(expression: exp.Expr, origin: dict[int, ColumnRef]) -> ColumnRef | None:
    """The catalog column this projection *is*, if it is one and not built."""
    inner = expression.this if isinstance(expression, exp.Alias) else expression
    if isinstance(inner, exp.Column):
        return origin.get(id(inner))
    return None


def _carries_masked_value(
    expression: exp.Expr, origin: dict[int, ColumnRef], masked: set[ColumnRef]
) -> bool:
    """Can a masked column's value be read out of this cell?"""
    for column in expression.find_all(exp.Column):
        ref = origin.get(id(column))
        if ref is None or ref not in masked:
            continue
        if not _inside_value_destroying_aggregate(column, expression):
            return True
    return False


def _inside_value_destroying_aggregate(column: exp.Column, root: exp.Expr) -> bool:
    node: exp.Expr | None = column.parent
    while node is not None and node is not root.parent:
        if isinstance(node, _VALUE_DESTROYING_AGGREGATES):
            return True
        node = node.parent
    return False


# --- The row cap, written into the statement the engine will run ---


def _bound_rows(qualified: exp.Expression, max_rows: int | None) -> int | None:
    """Clamp the outermost row limit, in place, and say what it ended up as."""
    if max_rows is None or not isinstance(qualified, exp.Query):
        return None

    existing = qualified.args.get("limit")
    current: int | None = None
    if isinstance(existing, exp.Limit) and isinstance(existing.expression, exp.Literal):
        with suppress(ValueError):
            current = int(existing.expression.name)

    effective = max_rows if current is None else min(current, max_rows)
    qualified.set("limit", exp.Limit(expression=exp.Literal.number(effective)))
    return effective


def _policy_index(catalog: Catalog) -> dict[tuple[str, str, str], str]:
    return {
        _key(ColumnRef(table.schema_name, table.table_name, column.name)): column.policy
        for table in catalog.tables
        for column in table.columns
    }


def _key(ref: ColumnRef) -> tuple[str, str, str]:
    return (ref.schema.lower(), ref.table.lower(), ref.column.lower())
