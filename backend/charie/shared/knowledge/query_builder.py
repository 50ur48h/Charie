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
    checked = {}
    for name, raw in pieces.items():
        try:
            checked[name] = check_fragment(raw)
        except RecipeError as err:
            raise QueryBuildError(f"The recipe's {name} is unusable: {err}") from err
    return checked


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


def build_query(
    recipe_key: str,
    recipes: dict[str, Recipe],
    request: QueryRequest,
    context: BuildContext,
) -> BuiltQuery:
    """Build one total for a date range. Splits, joins, ratios and top N
    arrive in later sub-phases; each raises its own refusal until then."""
    try:
        recipe = recipes[recipe_key]
    except KeyError:
        raise QueryBuildError(f"Unknown recipe `{recipe_key}`.") from None
    if recipe.kind == "ratio":
        raise QueryBuildError("Ratio numbers aren't supported yet.")
    if request.top_n is not None:
        raise QueryBuildError("Top N isn't supported yet.")
    if request.dimensions or request.filters:
        raise QueryBuildError("Splits and filters aren't supported yet.")
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
    where = [_period_condition(recipe, request.period, context)]
    where.extend(recipe.filters)
    sql = (
        f"SELECT {select} AS value FROM {recipe.table} AS {main_alias} WHERE {' AND '.join(where)}"
    )
    return BuiltQuery(
        sql=sql,
        recipe_key=recipe_key,
        columns=["value"],
        dimension_columns=[],
        is_ratio=False,
        overlapping_dimension=None,
    )
