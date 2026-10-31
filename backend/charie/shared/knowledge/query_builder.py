"""The query builder (P09.1): recipes to checked SQL, no AI-written queries.

Code builds the query from a recipe, so the AI never writes SQL for a
known business number. The checker still checks the result.
"""

import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from charie.shared.knowledge.recipe import FragmentInfo, Recipe, RecipeError, check_fragment


class QueryBuildError(ValueError):
    """The builder refuses this request, in plain English."""


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

    links: list[Any] = []
    required_filters: dict[str, list[str]] = {}
    forbidden_tables: list[str] = []
    time_zone: str = "UTC"
    week_starts: Literal["monday", "sunday"] = "monday"


class BuiltQuery(BaseModel):
    """A built query, ready for the checker."""

    model_config = ConfigDict(extra="forbid")

    sql: str
    recipe_key: str
    columns: list[str]
    dimension_columns: list[str]
    is_ratio: bool
    overlapping_dimension: str | None


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
    main_alias = recipe.table.split(".")[-1]
    for info in pieces.values():
        if any(table != main_alias for table in info.tables):
            raise QueryBuildError("This number needs a join, which isn't supported yet.")
    if recipe.aggregate == "count" and recipe.expression == "*":
        select = "COUNT(*)"
    elif recipe.aggregate == "count_distinct":
        select = f"COUNT(DISTINCT {recipe.expression})"
    else:
        select = f"SUM({recipe.expression})"
    outputs: list[str] = []
    groupers: list[str] = []
    for key in request.dimensions:
        dimension = _resolve_dimension(recipe, recipe_key, key)
        for output in _split_columns(recipe, dimension, context):
            outputs.append(output)
            groupers.append(output.rsplit(" AS ", 1)[0])
    where = [_period_condition(recipe, request.period, context)]
    where.extend(recipe.filters)
    where.extend(_request_filter(recipe, filtr) for filtr in request.filters)
    if groupers:
        sql = (
            f"SELECT {', '.join(outputs)}, {select} AS value "
            f"FROM {recipe.table} AS {main_alias} "
            f"WHERE {' AND '.join(where)} "
            f"GROUP BY {', '.join(groupers)} ORDER BY {', '.join(groupers)}"
        )
        dimension_columns = [output.rsplit(" AS ", 1)[1] for output in outputs]
    else:
        sql = (
            f"SELECT {select} AS value FROM {recipe.table} AS {main_alias} "
            f"WHERE {' AND '.join(where)}"
        )
        dimension_columns = []
    return BuiltQuery(
        sql=sql,
        recipe_key=recipe_key,
        columns=[*dimension_columns, "value"],
        dimension_columns=dimension_columns,
        is_ratio=False,
        overlapping_dimension=None,
    )
