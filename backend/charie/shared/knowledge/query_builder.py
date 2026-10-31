"""The query builder (P09.1): recipes to checked SQL, no AI-written queries.

Code builds the query from a recipe, so the AI never writes SQL for a
known business number. The checker still checks the result.
"""

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from charie.shared.knowledge.recipe import (
    DimensionDetails,
    DimensionProof,
    FragmentInfo,
    Recipe,
    RecipeError,
    check_fragment,
)


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


class BridgeGroup(BaseModel):
    """Links out of one table to different tables: counts may duplicate."""

    model_config = ConfigDict(extra="forbid")

    bridge: str
    links: list[JoinLink]


class OverlappingGroups(BaseModel):
    """Every bridge-table group in this build."""

    model_config = ConfigDict(extra="forbid")

    groups: list[BridgeGroup]


def identify_overlap(links: list[JoinLink]) -> OverlappingGroups | None:
    """Bridge-table groups: link pairs sharing a from_table, different to_tables."""
    by_from: dict[str, list[JoinLink]] = {}
    for link in links:
        by_from.setdefault(link.from_table, []).append(link)
    groups = [
        BridgeGroup(bridge=table, links=sorted(links, key=lambda link: link.to_table))
        for table, links in sorted(by_from.items())
        if len({link.to_table for link in links}) > 1
    ]
    return OverlappingGroups(groups=groups) if groups else None


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
    """What the builder may assume: tables, links, rules, time zone, week start."""

    model_config = ConfigDict(extra="forbid")

    tables: list[str] = []
    links: list[JoinLink] = []
    required_filters: dict[str, list[str]] = {}
    forbidden_tables: list[str] = []
    time_zone: str = "UTC"
    week_starts: Literal["monday", "sunday"] = "monday"
    dimension_details: dict[str, DimensionDetails] = {}


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
    pieces = {name: raw for name, raw in pieces.items() if raw and raw.strip()}
    if not pieces:
        raise QueryBuildError("The recipe has no expressions to build from.")
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


def _time_split(column: str, column_type: str | None, grain: str, context: BuildContext) -> str:
    """`CAST(date_trunc(...)) AS <grain>`; only instants shift to the zone."""
    if column_type == "timestamptz":
        column = f"{column} AT TIME ZONE '{context.time_zone}'"
    if context.week_starts == "sunday" and grain == "week":
        inner = f"date_trunc('week', {column} + INTERVAL '1 day') - INTERVAL '1 day'"
    else:
        inner = f"date_trunc('{grain}', {column})"
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
        return [_time_split(recipe.time_column, recipe.time_column_type, dimension.grain, context)]
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
            f"LEFT JOIN {other} AS {other_alias} ON {on(main_alias, oriented, other_alias)}"
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
            f"distinct {one_table}.{one_column}; "
            "rows without a match stay in the total and land in an empty group"
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


def _link_key(link: JoinLink) -> tuple[str, str, str, str]:
    """Sort key for one link, so equal paths always resolve the same way."""
    return (link.from_table, link.to_table, link.from_column, link.to_column)


def _many_to_one_step(current: str, link: JoinLink) -> tuple[str, str, str] | None:
    """Step past one tested link from its many side: next table and columns."""
    if not link.tested or link.from_table == link.to_table:
        return None
    if link.multiplicity == "many_to_one" and current == link.from_table:
        return (link.to_table, link.from_column, link.to_column)
    if link.multiplicity == "one_to_many" and current == link.to_table:
        return (link.from_table, link.to_column, link.from_column)
    return None


def _resolve_path(main_table: str, needed: str, links: list[JoinLink]) -> list[JoinLink] | None:
    """Shortest tested many-to-one path; ties go to the first link keys.

    Single tested hops keep their direction (the overlap case joins the
    many side on purpose). Direct untested links refuse; without any path
    the caller decides the refusal, so a hard rule is never silently lost.
    """
    if main_table == needed:
        return []
    direct = [
        link
        for link in links
        if {link.from_table, link.to_table} == {main_table, needed}
        and link.from_table != link.to_table
    ]
    tested = [link for link in direct if link.tested]
    if tested:
        oriented = _oriented_link(main_table, tested[0])
        if oriented is None:
            raise QueryBuildError("This number needs a join, which isn't supported yet.")
        return [oriented]
    if direct:
        raise QueryBuildError(f"The {needed} table needs a tested link to join on.")
    ordered = sorted(links, key=_link_key)
    frontier = [(main_table, [], {main_table})]
    while frontier:
        arrivals = []
        nxt_frontier = []
        for current, hops, seen in frontier:
            for link in ordered:
                step = _many_to_one_step(current, link)
                if step is None:
                    continue
                nxt = step[0]
                if nxt in seen:
                    continue
                nhops = (*hops, (link, step))
                if nxt == needed:
                    arrivals.append(nhops)
                else:
                    nxt_frontier.append((nxt, nhops, seen | {nxt}))
        if arrivals:
            keyed = min((tuple(_link_key(link) for link, _ in hops), hops) for hops in arrivals)
            path = []
            current = main_table
            for link, (_nxt, many_column, one_column) in keyed[1]:
                path.append(
                    JoinLink(
                        from_table=current,
                        to_table=_nxt,
                        from_column=many_column,
                        to_column=one_column,
                        multiplicity="many_to_one",
                        tested=True,
                        reason=link.reason,
                    )
                )
                current = _nxt
            return path
        frontier = nxt_frontier
    return None


def _resolve_ratio(recipe: Recipe, recipes: dict[str, Recipe]) -> tuple[Recipe, Recipe]:
    """The numerator and denominator recipes, or a refusal naming the gap."""
    title = recipe.title or "This ratio"
    sides = []
    for role in ("numerator", "denominator"):
        key = recipe.numerator if role == "numerator" else recipe.denominator
        try:
            side = recipes[key]
        except KeyError:
            raise QueryBuildError(f"{title} names an unknown {role} `{key}`.") from None
        if side.kind != "simple":
            raise QueryBuildError("Ratios divide simple recipes, not other ratios.")
        sides.append(side)
    return sides[0], sides[1]


def _overlap_proof(
    key: str, side: Recipe, side_key: str, context: BuildContext
) -> DimensionProof | None:
    """The validated uniqueness proof for this split, or None when plain."""
    details = context.dimension_details.get(key)
    if details is None or not details.unique_with:
        return None
    found = None
    for raw in details.unique_with:
        try:
            proof = raw if isinstance(raw, DimensionProof) else DimensionProof.model_validate(raw)
        except ValueError as err:
            raise QueryBuildError(f"The uniqueness proof for {key} is incomplete.") from err
        if proof.base_table == side.table:
            found = proof
    if found is None:
        raise QueryBuildError(f"The proof for {key} is about another table, not {side.table}.")
    if not found.exact:
        raise QueryBuildError(
            f"The uniqueness proof for {key} isn't exact, so the split is refused."
        )
    if not found.base_key_columns:
        raise QueryBuildError(f"The uniqueness proof for {key} names no base rows.")
    if not found.checked_at:
        raise QueryBuildError(f"The uniqueness proof for {key} has no check date.")
    dimension = _resolve_dimension(side, side_key, key)
    if found.dimension_expression != dimension.expression:
        raise QueryBuildError(f"The proof for {key} is about another expression.")
    _check_proof_path(side, dimension, found, context)
    return found


def _check_proof_path(
    side: Recipe, dimension, proof: DimensionProof, context: BuildContext
) -> None:
    """The proof's table path is one tested join per hop, ending at the split."""
    if not proof.link_keys:
        raise QueryBuildError("The uniqueness proof names no tested path.")
    if proof.link_keys[-1] != dimension.table:
        raise QueryBuildError("The uniqueness proof leads to another table.")
    previous = side.table
    for table in proof.link_keys:
        hop = [
            link
            for link in context.links
            if link.tested
            and link.from_table != link.to_table
            and {link.from_table, link.to_table} == {previous, table}
        ]
        if not hop:
            raise QueryBuildError("The uniqueness proof needs a tested link to join on.")
        previous = table


def _resolve_overlap(
    request: QueryRequest,
    sides: list[Recipe],
    side_keys: list[str],
    context: BuildContext,
) -> tuple[str, DimensionProof] | None:
    """At most one overlapping split per request, with its validated proof."""
    found: tuple[str, DimensionProof] | None = None
    for key in request.dimensions:
        proof = _overlap_proof(key, sides[0], side_keys[0], context)
        if proof is None:
            continue
        if found is not None:
            raise QueryBuildError("Only one overlapping split is allowed at a time.")
        if len(sides) > 1:
            raise QueryBuildError("Overlapping splits can't be combined with a ratio yet.")
        found = (key, proof)
    return found


def build_query(
    recipe_key: str,
    recipes: dict[str, Recipe],
    request: QueryRequest,
    context: BuildContext,
) -> BuiltQuery:
    """Build a total, a split, a ratio, or a top N list for a date range."""
    try:
        recipe = recipes[recipe_key]
    except KeyError:
        raise QueryBuildError(f"Unknown recipe `{recipe_key}`.") from None
    sides = [recipe]
    side_keys = [recipe_key]
    if recipe.kind == "ratio":
        if recipe.filters:
            raise QueryBuildError("Ratios take no filters of their own; filter each side.")
        sides = list(_resolve_ratio(recipe, recipes))
        side_keys = [recipe.numerator, recipe.denominator]
        units = {sides[0].unit, sides[1].unit}
        if units != {"money", "count"} and len(units) > 1:
            raise QueryBuildError("A ratio needs its recipes to share a unit.")
        if sides[0].time_column != sides[1].time_column:
            raise QueryBuildError("A ratio needs its recipes on the same time column.")
    if request.top_n is not None and request.top_n.n < 1:
        raise QueryBuildError("Top N needs a positive whole number.")
    if request.top_n is not None and not request.dimensions:
        raise QueryBuildError("Top N needs a split to rank.")
    if request.period is None:
        raise QueryBuildError("Totals need a date range.")
    overlap = _resolve_overlap(request, sides, side_keys, context)
    if recipe.kind == "ratio":
        return _build_ratio(recipe_key, recipe, sides, side_keys, request, context)
    result = _build_simple(sides[0], side_keys[0], request, context, overlap, apply_ranking=True)
    return BuiltQuery(
        sql=result.sql,
        recipe_key=recipe_key,
        columns=[*result.dimension_columns, "value"],
        dimension_columns=result.dimension_columns,
        is_ratio=False,
        overlapping_dimension=overlap[0] if overlap is not None else None,
        proof=result.proof,
    )


class _SideResult(BaseModel):
    """One aggregated side: its SQL, split columns, groupers and proof."""

    model_config = ConfigDict(extra="forbid")

    sql: str
    dimension_columns: list[str] = []
    groupers: list[str] = []
    proof: list[str] = []


def _ranked(sql: str, dimension_columns: list[str], top_n: TopN) -> str:
    """Keep the first N groups after full aggregation, ties broken by split."""
    tiebreak = ", ".join(dimension_columns)
    return f"{sql} ORDER BY value DESC NULLS LAST, {tiebreak} LIMIT {top_n.n}"


def _build_simple(
    side: Recipe,
    side_key: str,
    request: QueryRequest,
    context: BuildContext,
    overlap: tuple[str, DimensionProof] | None,
    apply_ranking: bool = False,
) -> _SideResult:
    """One simple recipe as SQL: a total, a split, or a deduplicated split."""
    pieces = _check_pieces(side)
    if side.table in context.forbidden_tables:
        raise QueryBuildError(f"The {side.table} table is outside the tenant's data.")
    requested = [_resolve_dimension(side, side_key, key) for key in request.dimensions]
    for filtr in request.filters:
        if filtr.dimension in GRAINS:
            continue
        filtr_dimension = _resolve_dimension(side, side_key, filtr.dimension)
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
    main_alias = builder.add(side.table)
    main_bare = side.table.split(".")[-1]

    def full_table(bare: str) -> str | None:
        if bare == main_bare:
            return side.table
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
    for index in range(len(side.filters)):
        fragment_tables.update(pieces[f"filter {index + 1}"].tables)
    for dimension in requested:
        if dimension.table and dimension.table != side.table and dimension.table not in needed:
            needed.append(dimension.table)
        fragment_tables.update(pieces[f"dimension {dimension.key}"].tables)
        label_piece = pieces.get(f"dimension {dimension.key} label")
        if label_piece is not None:
            fragment_tables.update(label_piece.tables)
    for bare in sorted(fragment_tables):
        full = full_table(bare)
        if full is None:
            raise QueryBuildError("This number needs a join, which isn't supported yet.")
        if full != side.table and full not in needed:
            needed.append(full)
    for table in sorted(context.required_filters):
        if table == side.table or table in needed:
            continue
        if table in context.forbidden_tables:
            raise QueryBuildError(f"The {table} table is outside the tenant's data.")
        if table in SYSTEM_TABLES:
            raise QueryBuildError(f"The {table} table is a system table, not a dimension.")
        needed.append(table)
    dim_key_by_table = {}
    for dimension in requested:
        if dimension.table and dimension.table != side.table:
            dim_key_by_table.setdefault(dimension.table, dimension.key)
    overlap_table = None
    if overlap is not None:
        overlap_table = _resolve_dimension(side, side_key, overlap[0]).table
    title = side.title or side_key

    def refuse(table: str) -> None:
        if table in context.required_filters:
            raise QueryBuildError(f"Can't enforce the hard rule on {table} from {side.table}.")
        key = dim_key_by_table.get(table)
        if key is not None:
            raise QueryBuildError(
                f'"{title}" can\'t be split by {key}: one {side.table} row '
                f"has many {table}, so it would count some rows more than once."
            )
        raise QueryBuildError("This number needs a join, which isn't supported yet.")

    for table in needed:
        hops = _resolve_path(side.table, table, context.links)
        if table == overlap_table:
            if hops is None or len(hops) != 1:
                raise QueryBuildError("This number needs a join, which isn't supported yet.")
        else:
            if hops is None:
                refuse(table)
            assert hops is not None
            if any(hop.multiplicity != "many_to_one" for hop in hops):
                refuse(table)
        assert hops is not None
        current_table, current_alias = side.table, main_alias
        for hop in hops:
            assert hop.from_table == current_table
            nxt = hop.to_table
            if nxt in context.forbidden_tables:
                raise QueryBuildError(f"The {nxt} table is outside the tenant's data.")
            if nxt in SYSTEM_TABLES:
                raise QueryBuildError(f"The {nxt} table is a system table, not a dimension.")
            if nxt in builder.aliases:
                current_alias = builder.aliases[nxt]
            else:
                current_alias = builder.join(current_table, current_alias, hop)
            current_table = nxt
    bare_tables: dict[str, str] = {}
    for full in builder.aliases:
        bare = full.split(".")[-1]
        if bare in bare_tables and bare_tables[bare] != full:
            raise QueryBuildError(
                f"The tables {bare_tables[bare]} and {full} share a name, "
                "so Charie can't tell their columns apart."
            )
        bare_tables[bare] = full
    aliases = {
        full.split(".")[-1]: alias
        for full, alias in builder.aliases.items()
        if alias != full.split(".")[-1]
    }

    def qualified(text: str) -> str:
        for bare, alias in aliases.items():
            text = text.replace(f"{bare}.", f"{alias}.")
        return text

    if side.aggregate == "count" and side.expression == "*":
        select = "COUNT(*)"
        inner_measure = ""
        outer_measure = "COUNT(*)"
    elif side.aggregate == "count":
        select = f"COUNT({qualified(side.expression)})"
        inner_measure = qualified(side.expression)
        outer_measure = "COUNT(m)"
    elif side.aggregate == "count_distinct":
        select = f"COUNT(DISTINCT {qualified(side.expression)})"
        inner_measure = qualified(side.expression)
        outer_measure = "COUNT(DISTINCT m)"
    else:
        select = f"SUM({qualified(side.expression)})"
        inner_measure = qualified(side.expression)
        outer_measure = "SUM(m)"
    outputs: list[str] = []
    groupers: list[str] = []
    for key in request.dimensions:
        dimension = _resolve_dimension(side, side_key, key)
        for output in _split_columns(side, dimension, context):
            outputs.append(qualified(output))
            groupers.append(qualified(output).rsplit(" AS ", 1)[0])
    where = [qualified(_period_condition(side, request.period, context))]
    where.extend(qualified(raw) for raw in side.filters)
    where.extend(qualified(_request_filter(side, filtr)) for filtr in request.filters)
    for table in [side.table, *builder.aliases]:
        where.extend(qualified(raw) for raw in context.required_filters.get(table, []))
    tables = f"FROM {side.table} AS {main_alias}"
    if builder.joins:
        tables += " " + " ".join(builder.joins)
    proof = list(builder.proof)
    if overlap is not None:
        key, found = overlap
        keys = [f"{main_alias}.{column}" for column in found.base_key_columns]
        inner_columns = [*keys, *outputs]
        if inner_measure:
            inner_columns.append(f"{inner_measure} AS m")
        inner = f"SELECT DISTINCT {', '.join(inner_columns)} {tables} WHERE {' AND '.join(where)}"
        dimension_columns = [output.rsplit(" AS ", 1)[1] for output in outputs]
        sql = (
            f"SELECT {', '.join(dimension_columns)}, {outer_measure} AS value "
            f"FROM ({inner}) AS overlap GROUP BY {', '.join(dimension_columns)}"
        )
        proof.append(
            f"Splits by {key} overlap: each {side.table} row counts once per "
            "group after deduplication, so the groups don't add up to the total."
        )
        if apply_ranking and request.top_n is not None:
            sql = _ranked(sql, dimension_columns, request.top_n)
        elif groupers:
            sql += f" ORDER BY {', '.join(dimension_columns)}"
        return _SideResult(
            sql=sql, dimension_columns=dimension_columns, groupers=dimension_columns, proof=proof
        )
    if groupers:
        sql = (
            f"SELECT {', '.join(outputs)}, {select} AS value "
            f"{tables} "
            f"WHERE {' AND '.join(where)} "
            f"GROUP BY {', '.join(groupers)}"
        )
        if apply_ranking and request.top_n is not None:
            dimension_columns = [output.rsplit(" AS ", 1)[1] for output in outputs]
            sql = _ranked(sql, dimension_columns, request.top_n)
        else:
            sql += f" ORDER BY {', '.join(groupers)}"
            dimension_columns = [output.rsplit(" AS ", 1)[1] for output in outputs]
    else:
        sql = f"SELECT {select} AS value {tables} WHERE {' AND '.join(where)}"
        dimension_columns = []
    return _SideResult(sql=sql, dimension_columns=dimension_columns, groupers=groupers, proof=proof)


def _build_ratio(
    recipe_key: str,
    recipe: Recipe,
    sides: list[Recipe],
    side_keys: list[str],
    request: QueryRequest,
    context: BuildContext,
) -> BuiltQuery:
    """Two separately aggregated sides, divided after alignment, never mixed."""
    numerator, denominator = sides
    num = _build_simple(numerator, side_keys[0], request, context, None)
    den = _build_simple(denominator, side_keys[1], request, context, None)
    if num.dimension_columns != den.dimension_columns or num.groupers != den.groupers:
        raise QueryBuildError("The ratio sides split differently, so they can't be divided.")
    names = [
        numerator.title or side_keys[0],
        denominator.title or side_keys[1],
    ]
    proof = [
        f"Divides {names[0]} by {names[1]} at the same splits; each side is "
        "added up on its own before dividing, so nothing counts twice.",
        "Zero denominators are null, not zero.",
        *num.proof,
        *den.proof,
    ]
    divide = "CAST(num.value AS NUMERIC) / NULLIF(den.value, 0)"
    if recipe.unit == "percent":
        divide += " * 100"
        proof.append("Shown as points out of 100.")
    if not num.dimension_columns:
        sql = f"SELECT CAST(({num.sql}) AS NUMERIC) / NULLIF(({den.sql}), 0)"
        if recipe.unit == "percent":
            sql += " * 100"
        return BuiltQuery(
            sql=f"{sql} AS value",
            recipe_key=recipe_key,
            columns=["value"],
            dimension_columns=[],
            is_ratio=True,
            overlapping_dimension=None,
            proof=proof,
        )
    # Plain equality: Postgres only runs FULL JOIN on merge- or
    # hash-joinable conditions. A null group key stays unmatched, so its
    # ratio is null, never zero-filled or silently dropped.
    pairs = " AND ".join(f"num.{column} = den.{column}" for column in num.dimension_columns)
    aligned = ", ".join(
        f"COALESCE(num.{column}, den.{column}) AS {column}" for column in num.dimension_columns
    )
    sql = (
        f"SELECT {aligned}, {divide} AS value "
        f"FROM ({num.sql}) AS num FULL OUTER JOIN ({den.sql}) AS den ON {pairs}"
    )
    if request.top_n is not None:
        sql = _ranked(sql, num.dimension_columns, request.top_n)
    else:
        sql += f" ORDER BY {', '.join(num.dimension_columns)}"
    return BuiltQuery(
        sql=sql,
        recipe_key=recipe_key,
        columns=[*num.dimension_columns, "value"],
        dimension_columns=num.dimension_columns,
        is_ratio=True,
        overlapping_dimension=None,
        proof=proof,
    )


def load_build_context(session, version_id: int, time_zone: str = "UTC") -> BuildContext:
    """The builder's context from learned knowledge (P09.3).

    Tested many-to-one links become joins; anything else (untested,
    one-to-one, multi-column) is left out rather than guessed. Hard rules
    become required filters and forbidden tables. The same knowledge
    always builds the same context.
    """
    from charie.shared.knowledge import catalog as knowledge_catalog
    from charie.shared.knowledge.calendar import CALENDAR_KEY
    from charie.shared.knowledge.store import get_entry, list_entries
    from charie.shared.safety.catalog import required_filters_for

    links: list[JoinLink] = []
    for entry in list_entries(session, version_id, kinds=["link"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if not details.get("tested_at"):
            continue
        from_table = details.get("from_table") or ""
        to_table = details.get("to_table") or ""
        from_columns = details.get("from_columns") or []
        to_columns = details.get("to_columns") or []
        if not from_table or not to_table:
            continue
        if len(from_columns) != 1 or len(to_columns) != 1:
            continue
        if details.get("cardinality") != "many_to_one":
            continue
        links.append(
            JoinLink(
                from_table=from_table,
                to_table=to_table,
                from_column=from_columns[0],
                to_column=to_columns[0],
                multiplicity="many_to_one",
                tested=True,
                reason=entry.meaning or "",
            )
        )
    links.sort(key=lambda link: (link.from_table, link.to_table, link.from_column, link.to_column))
    known = knowledge_catalog.build_catalog(session, version_id)
    required: dict[str, list[str]] = {}
    for table in sorted(known.tables):
        filters = required_filters_for(known, [table])
        if filters:
            required[table] = filters
    forbidden = sorted(knowledge_catalog.forbidden_tables(session, version_id))
    dimension_details: dict[str, DimensionDetails] = {}
    for entry in list_entries(session, version_id, kinds=["dimension"]):
        dimension_details[entry.key] = DimensionDetails.model_validate(entry.details or {})
    week_starts: Literal["monday", "sunday"] = "monday"
    learned_calendar = get_entry(session, version_id, CALENDAR_KEY)
    learned_details = learned_calendar.details if learned_calendar is not None else None
    if isinstance(learned_details, dict) and learned_details.get("week_start") == "sunday":
        week_starts = "sunday"
    return BuildContext(
        tables=sorted(known.tables),
        links=links,
        required_filters=required,
        forbidden_tables=forbidden,
        time_zone=time_zone or "UTC",
        week_starts=week_starts,
        dimension_details=dimension_details,
    )
