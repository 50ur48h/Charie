"""The query builder (P09.1): recipes to checked SQL, no AI-written queries.

Code builds the query from a recipe, so the AI never writes SQL for a
known business number. The checker still checks the result.
"""

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from charie.shared.knowledge.recipe import FragmentInfo, Recipe, RecipeError, check_fragment


class QueryBuildError(ValueError):
    """The builder refuses this request, in plain English."""


class JoinLink(BaseModel):
    """One tested join between two tables, both directions allowed."""

    model_config = ConfigDict(extra="forbid")

    from_table: str
    to_table: str
    from_column: str
    to_column: str
    multiplicity: Literal["many_to_one", "one_to_many"]
    tested: bool = True
    reason: str = ""


def on(from_alias: str, link: JoinLink, to_alias: str) -> str:
    """The join condition, one row on the one side, many on the many side."""
    if link.multiplicity == "many_to_one":
        one_alias, one_column = to_alias, link.to_column
        many_alias, many_column = from_alias, link.from_column
    else:
        one_alias, one_column = from_alias, link.from_column
        many_alias, many_column = to_alias, link.to_column
    return f"{one_alias}.{one_column} = {many_alias}.{many_column}"


class DateRange(BaseModel):
    """An inclusive date range, `YYYY-MM-DD` on both ends."""

    model_config = ConfigDict(extra="forbid")

    start: str
    end: str


class QueryFilter(BaseModel):
    """Keep only rows whose dimension expression is (not) in these values."""

    model_config = ConfigDict(extra="forbid")

    dimension: str
    op: Literal["in", "not_in"]
    values: list[str | int | float]


class TopN(BaseModel):
    """Keep the first N groups after full aggregation."""

    model_config = ConfigDict(extra="forbid")

    n: int


class QueryRequest(BaseModel):
    """What to calculate: a period, optional splits, filters and top N."""

    model_config = ConfigDict(extra="forbid")

    period: DateRange | None = None
    dimensions: list[str] = []
    filters: list[QueryFilter] = []
    top_n: TopN | None = None


class BuildContext(BaseModel):
    """What the builder may assume: links, rules, time zone, week start."""

    model_config = ConfigDict(extra="forbid")

    links: list[JoinLink] = []
    required_filters: dict[str, list[str]] = {}
    forbidden_tables: list[str] = []
    time_zone: str = "UTC"
    week_starts: Literal["monday", "sunday"] = "monday"


#: Tables dimensions may never read: migrations and bookkeeping, not business.
SYSTEM_TABLES = frozenset({"shop.migrations", "shop.alembic_version"})


class BuiltQuery(BaseModel):
    """A built query, ready for the checker."""

    model_config = ConfigDict(extra="forbid")

    sql: str
    recipe_key: str
    columns: list[str]
    dimension_columns: list[str]
    is_ratio: bool
    overlapping_dimension: str | None
    proof: list[str] = []


def _check_pieces(recipe: Recipe) -> dict[str, FragmentInfo]:
    """Check the recipe's expressions; refuses joins the builder can't do."""
    pieces = {"expression": recipe.expression, "time_column": recipe.time_column}
    for index, raw in enumerate(recipe.filters):
        pieces[f"filter {index + 1}"] = raw
    for dimension in recipe.dimensions:
        pieces[f"dimension {dimension.key}"] = dimension.expression
        if dimension.label_expression:
            pieces[f"dimension {dimension.key} label"] = dimension.label_expression
    checked = {}
    for name, raw in pieces.items():
        try:
            checked[name] = check_fragment(raw)
        except RecipeError as err:
            raise QueryBuildError(f"The recipe's {name} is unusable: {err}") from err
    return checked


def sql_literal(value: str | int | float) -> str:
    """One filter value as SQL: text gets single quotes, numbers stay bare."""
    if isinstance(value, bool):
        raise QueryBuildError("Only text, whole numbers and decimals can be used to filter.")
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    raise QueryBuildError("Only text, whole numbers and decimals can be used to filter.")


def _time_split(column: str, grain: str, context: BuildContext) -> str:
    """`CAST(date_trunc(...)) AS <grain>`, in the business time zone."""
    zoned = f"{column} AT TIME ZONE '{context.time_zone}'"
    if context.week_starts == "sunday" and grain == "week":
        inner = f"date_trunc('week', {zoned} + INTERVAL '1 day') - INTERVAL '1 day'"
    else:
        inner = f"date_trunc('{grain}', {zoned})"
    return f"CAST({inner} AS DATE) AS {grain}"


def _period_condition(recipe: Recipe, period: DateRange, context: BuildContext) -> str:
    """`from the start, and before the day after the end`, in the column type."""
    try:
        last = datetime.date.fromisoformat(period.end)
        first = datetime.date.fromisoformat(period.start)
    except ValueError as err:
        raise QueryBuildError("The period needs `YYYY-MM-DD` dates.") from err
    if last < first:
        raise QueryBuildError("The period ends before it starts.")
    after = last + datetime.timedelta(days=1)
    column = recipe.time_column
    if recipe.time_column_type == "date":
        start_lit = f"CAST('{first.isoformat()}' AS DATE)"
        end_lit = f"CAST('{after.isoformat()}' AS DATE)"
    elif recipe.time_column_type == "timestamp":
        start_lit = f"CAST('{first.isoformat()} 00:00:00' AS TIMESTAMP)"
        end_lit = f"CAST('{after.isoformat()} 00:00:00' AS TIMESTAMP)"
    else:
        zone = context.time_zone
        start_lit = f"CAST('{first.isoformat()} 00:00:00 {zone}' AS TIMESTAMPTZ)"
        end_lit = f"CAST('{after.isoformat()} 00:00:00 {zone}' AS TIMESTAMPTZ)"
    return f"{column} >= {start_lit} AND {column} < {end_lit}"


GRAINS = ("day", "week", "month", "quarter", "year")


def _resolve_dimension(recipe: Recipe, recipe_key: str, key: str):
    """The recipe's dimension for this key, or a refusal naming it."""
    title = recipe.title or recipe_key
    for dimension in recipe.dimensions:
        if dimension.key == key:
            return dimension
    raise QueryBuildError(f'"{title}" can\'t be split by {key}.')


def _split_columns(recipe: Recipe, dimension, context: BuildContext) -> list[str]:
    """The output columns for one requested split."""
    if dimension.kind == "time":
        if not dimension.grain:
            raise QueryBuildError("Time dimensions need a grain to split by.")
        return [_time_split(recipe.time_column, dimension.grain, context)]
    name = dimension.key.split(".")[-1]
    columns = [f"{dimension.expression} AS {name}"]
    if dimension.label_expression:
        columns.append(f"{dimension.label_expression} AS {name}_label")
    return columns


def _request_filter(recipe: Recipe, filtr: QueryFilter) -> str:
    """One `IN` / `NOT IN` condition against the dimension's expression."""
    if filtr.dimension in GRAINS:
        raise QueryBuildError(f"Use the period to pick dates, not a filter on {filtr.dimension}.")
    for dimension in recipe.dimensions:
        if dimension.key == filtr.dimension:
            if dimension.kind == "time":
                raise QueryBuildError(
                    f"Use the period to pick dates, not a filter on {dimension.grain}."
                )
            values = ", ".join(sql_literal(value) for value in filtr.values)
            keyword = "IN" if filtr.op == "in" else "NOT IN"
            return f"{dimension.expression} {keyword} ({values})"
    raise QueryBuildError(f"Unknown dimension `{filtr.dimension}`.")


class JoinBuilder:
    """Aliases and joins for one build; the same table never joins twice."""

    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}
        self.joins: list[str] = []
        self.proof: list[str] = []
        self._generated = 2

    def add(self, table: str) -> str:
        """The alias for this table; a second join of it is refused."""
        if table in self.aliases:
            raise QueryBuildError(f"There is already a table called {self.aliases[table]}.")
        base = table.split(".")[-1]
        taken = set(self.aliases.values())
        if len(base) < 2 or base[0].isdigit() or base in taken:
            base = self._fresh_alias(taken)
        self.aliases[table] = base
        return base

    def _fresh_alias(self, taken: set[str]) -> str:
        while True:
            alias = f"table_{self._generated}"
            self._generated += 1
            if alias not in taken:
                return alias

    def join(self, main_table: str, main_alias: str, link: JoinLink) -> str:
        """Join the link's other table to the main table; returns its alias."""
        oriented = _oriented_link(main_table, link)
        if oriented is None:
            raise QueryBuildError("This number needs a join, which isn't supported yet.")
        other = oriented.to_table
        other_alias = self.add(other)
        self.joins.append(
            f"JOIN {other} AS {other_alias} ON {on(main_alias, oriented, other_alias)}"
        )
        one_table = (
            oriented.to_table if oriented.multiplicity == "many_to_one" else oriented.from_table
        )
        one_column = (
            oriented.to_column if oriented.multiplicity == "many_to_one" else oriented.from_column
        )
        self.proof.append(
            f"{other} joins {main_table} on the tested {link.multiplicity} link "
            f"{link.from_table}.{link.from_column} = {link.to_table}.{link.to_column}; "
            f"distinct {one_table}.{one_column}"
        )
        return other_alias


def _oriented_link(main_table: str, link: JoinLink) -> JoinLink | None:
    """The link with the main table on the from side, or None if it self-joins."""
    if link.from_table == link.to_table:
        return None
    if link.from_table == main_table:
        return link
    if link.to_table == main_table:
        return link.model_copy(
            update={
                "from_table": link.to_table,
                "to_table": link.from_table,
                "from_column": link.to_column,
                "to_column": link.from_column,
                "multiplicity": (
                    "one_to_many" if link.multiplicity == "many_to_one" else "many_to_one"
                ),
            }
        )
    return None


def _resolve_join(main_table: str, needed: str, links: list[JoinLink]) -> JoinLink:
    """One tested hop from the main table, or the exact refusal for why not."""
    direct = [link for link in links if {link.from_table, link.to_table} == {main_table, needed}]
    tested = [link for link in direct if link.tested]
    if tested:
        oriented = _oriented_link(main_table, tested[0])
        if oriented is None:
            raise QueryBuildError("This number needs a join, which isn't supported yet.")
        return oriented
    if direct:
        raise QueryBuildError(f"The {needed} table needs a tested link to join on.")
    reached = {main_table}
    frontier = [main_table]
    while frontier:
        current = frontier.pop()
        for link in links:
            if not link.tested or link.from_table == link.to_table:
                continue
            other = None
            if link.from_table == current and link.to_table not in reached:
                other = link.to_table
            elif link.to_table == current and link.from_table not in reached:
                other = link.from_table
            if other is not None:
                if other == needed:
                    raise QueryBuildError(
                        "This question needs more than one join, which isn't supported yet."
                    )
                reached.add(other)
                frontier.append(other)
    raise QueryBuildError("This number needs a join, which isn't supported yet.")


def build_query(
    recipe_key: str,
    recipes: dict[str, Recipe],
    request: QueryRequest,
    context: BuildContext,
) -> BuiltQuery:
    """Build a total, a split, or a time split for a date range. Joins,
    ratios and top N arrive in later sub-phases; each raises its own
    refusal until then."""
    try:
        recipe = recipes[recipe_key]
    except KeyError:
        raise QueryBuildError(f"Unknown recipe `{recipe_key}`.") from None
    if recipe.kind == "ratio":
        raise QueryBuildError("Ratio numbers aren't supported yet.")
    if request.top_n is not None:
        raise QueryBuildError("Top N isn't supported yet.")
    if request.period is None:
        raise QueryBuildError("Totals need a date range.")
    pieces = _check_pieces(recipe)
    if recipe.table in context.forbidden_tables:
        raise QueryBuildError(f"The {recipe.table} table is outside the tenant's data.")
    requested = [_resolve_dimension(recipe, recipe_key, key) for key in request.dimensions]
    for filtr in request.filters:
        if filtr.dimension in GRAINS:
            continue
        filtr_dimension = _resolve_dimension(recipe, recipe_key, filtr.dimension)
        if filtr_dimension.kind != "time" and filtr_dimension not in requested:
            requested.append(filtr_dimension)
    for dimension in requested:
        if dimension.table in context.forbidden_tables:
            raise QueryBuildError(f"The {dimension.table} table is outside the tenant's data.")
        if dimension.table in SYSTEM_TABLES:
            raise QueryBuildError(
                f"The {dimension.table} table is a system table, not a dimension."
            )
    builder = JoinBuilder()
    main_alias = builder.add(recipe.table)
    main_bare = recipe.table.split(".")[-1]

    def full_table(bare: str) -> str | None:
        if bare == main_bare:
            return recipe.table
        for link in context.links:
            if link.from_table.split(".")[-1] == bare:
                return link.from_table
            if link.to_table.split(".")[-1] == bare:
                return link.to_table
        return None

    needed: list[str] = []
    fragment_tables: set[str] = set()
    for piece in ["expression", "time_column"]:
        fragment_tables.update(pieces[piece].tables)
    for index in range(len(recipe.filters)):
        fragment_tables.update(pieces[f"filter {index + 1}"].tables)
    for dimension in requested:
        if dimension.table and dimension.table != recipe.table and dimension.table not in needed:
            needed.append(dimension.table)
        fragment_tables.update(pieces[f"dimension {dimension.key}"].tables)
        label_piece = pieces.get(f"dimension {dimension.key} label")
        if label_piece is not None:
            fragment_tables.update(label_piece.tables)
    for bare in sorted(fragment_tables):
        full = full_table(bare)
        if full is None:
            raise QueryBuildError("This number needs a join, which isn't supported yet.")
        if full != recipe.table and full not in needed:
            needed.append(full)
    for table in needed:
        link = _resolve_join(recipe.table, table, context.links)
        builder.join(recipe.table, main_alias, link)
    aliases = {
        full.split(".")[-1]: alias
        for full, alias in builder.aliases.items()
        if alias != full.split(".")[-1]
    }

    def qualified(text: str) -> str:
        for bare, alias in aliases.items():
            text = text.replace(f"{bare}.", f"{alias}.")
        return text

    if recipe.aggregate == "count" and recipe.expression == "*":
        select = "COUNT(*)"
    elif recipe.aggregate == "count_distinct":
        select = f"COUNT(DISTINCT {qualified(recipe.expression)})"
    else:
        select = f"SUM({qualified(recipe.expression)})"
    outputs: list[str] = []
    groupers: list[str] = []
    for key in request.dimensions:
        dimension = _resolve_dimension(recipe, recipe_key, key)
        for output in _split_columns(recipe, dimension, context):
            outputs.append(qualified(output))
            groupers.append(qualified(output).rsplit(" AS ", 1)[0])
    where = [qualified(_period_condition(recipe, request.period, context))]
    where.extend(qualified(raw) for raw in recipe.filters)
    where.extend(qualified(_request_filter(recipe, filtr)) for filtr in request.filters)
    for table in [recipe.table, *builder.aliases]:
        where.extend(qualified(raw) for raw in context.required_filters.get(table, []))
    tables = f"FROM {recipe.table} AS {main_alias}"
    if builder.joins:
        tables += " " + " ".join(builder.joins)
    if groupers:
        sql = (
            f"SELECT {', '.join(outputs)}, {select} AS value "
            f"{tables} "
            f"WHERE {' AND '.join(where)} "
            f"GROUP BY {', '.join(groupers)} ORDER BY {', '.join(groupers)}"
        )
        dimension_columns = [output.rsplit(" AS ", 1)[1] for output in outputs]
    else:
        sql = f"SELECT {select} AS value {tables} WHERE {' AND '.join(where)}"
        dimension_columns = []
    return BuiltQuery(
        sql=sql,
        recipe_key=recipe_key,
        columns=[*dimension_columns, "value"],
        dimension_columns=dimension_columns,
        is_ratio=False,
        overlapping_dimension=None,
        proof=builder.proof,
    )
