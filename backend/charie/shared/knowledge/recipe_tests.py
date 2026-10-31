"""Recipe checks: does one business number hold up (P09.3c).

Four checks per recipe: the query runs; the number is believable for its
unit; any reported document number for the same metric, unit and period
matches at the fact's written precision; the splits add up to the total.
Code runs everything; the AI never sees the numbers.
"""

import calendar
import re
from collections.abc import Callable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict

from charie.shared.knowledge.query_builder import (
    BuildContext,
    DateRange,
    QueryRequest,
    build_query,
)
from charie.shared.knowledge.recipe import Recipe, RecipeCheck, ReportedCheck
from charie.shared.safety.catalog import Catalog, Link, RequiredFilter
from charie.shared.safety.sql_check import check_sql

Runner = Callable[[str], Sequence[Sequence[Any]]]


class ParsedNumber(BaseModel):
    """One reported number with its unit, period and precision."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    topic: str
    text: str
    amount: Decimal
    places: int
    unit: str
    start: str
    end: str


MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
QUARTERS = {"q1": 1, "q2": 4, "q3": 7, "q4": 10}

_AMOUNT = re.compile(
    r"(?P<money>\$[\d,]+(?:\.\d+)?)|(?P<percent>[\d,]+(?:\.\d+)?\s*(?:%|percent))|(?P<count>[\d,]+(?:\.\d+)?)"
)
_PERIOD = re.compile(
    r"(?P<month>[A-Za-z]+)\s+(?P<year>(?:19|20)\d{2})"
    r"|(?P<quarter>[Qq][1-4])\s+(?P<qyear>(?:19|20)\d{2})"
    r"|\b(?P<only_year>(?:19|20)\d{2})\b"
)


def _parse_amount(statement: str) -> tuple[Decimal, int, str] | None:
    """First amount in the statement, with its precision and unit."""
    match = _AMOUNT.search(statement)
    if match is None:
        return None
    if match.group("money") is not None:
        raw, unit = match.group("money")[1:], "money"
    elif match.group("percent") is not None:
        raw = re.sub(r"\s*(%|percent)$", "", match.group("percent").strip())
        unit = "percent"
    else:
        raw, unit = (match.group("count") or ""), "count"
    raw = raw.replace(",", "")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None
    places = len(raw.split(".")[1]) if "." in raw else 0
    return amount, places, unit


def _parse_period(statement: str) -> tuple[str, str] | None:
    """Month, quarter or year in the statement, as an inclusive range."""
    match = _PERIOD.search(statement)
    if match is None:
        return None
    if match.group("month") is not None:
        month = MONTHS.get(match.group("month").lower())
        if month is None:
            return None
        year = int(match.group("year"))
        last = calendar.monthrange(year, month)[1]
        return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"
    if match.group("quarter") is not None:
        year = int(match.group("qyear"))
        first = QUARTERS[match.group("quarter").lower()]
        last_month = first + 2
        last = calendar.monthrange(year, last_month)[1]
        return f"{year}-{first:02d}-01", f"{year}-{last_month:02d}-{last:02d}"
    year = int(match.group("only_year") or 0)
    return f"{year}-01-01", f"{year}-12-31"


def parse_reported_numbers(facts: Sequence[dict]) -> list[ParsedNumber]:
    """Reported numbers the checks can compare, oldest fact first."""
    parsed = []
    for fact in facts:
        statement = str(fact.get("statement") or "")
        amount = _parse_amount(statement)
        period = _parse_period(statement)
        if amount is None or period is None:
            continue
        value, places, unit = amount
        parsed.append(
            ParsedNumber(
                fact_id=str(fact.get("fact_id") or fact.get("id") or ""),
                topic=str(fact.get("topic") or ""),
                text=statement,
                amount=value,
                places=places,
                unit=unit,
                start=period[0],
                end=period[1],
            )
        )
    return parsed


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2}


def _number(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _catalog(context: BuildContext, tables: set[str]) -> Catalog:
    links = []
    for link in context.links:
        if not link.tested or link.from_table == link.to_table:
            continue
        if link.multiplicity == "many_to_one":
            links.append(
                Link(
                    one_table=link.to_table,
                    one_column=link.to_column,
                    many_table=link.from_table,
                    many_column=link.from_column,
                )
            )
        else:
            links.append(
                Link(
                    one_table=link.from_table,
                    one_column=link.from_column,
                    many_table=link.to_table,
                    many_column=link.to_column,
                )
            )
    required = [
        RequiredFilter(table=table, sql=sql, reason="a hard rule")
        for table, sqls in context.required_filters.items()
        for sql in sqls
    ]
    return Catalog(
        tables=sorted(tables),
        forbidden_tables=list(context.forbidden_tables),
        required_filters=required,
        links=links,
    )


def _run_total(
    side: Recipe, recipes: dict[str, Recipe], period: DateRange, context: BuildContext, run: Runner
) -> tuple[Decimal | None, str, str]:
    """Total for one side: value, checked SQL and refusal text."""
    built = build_query(
        "check",
        {**recipes, "check": side},
        QueryRequest(period=period),
        context,
    )
    tables = {side.table}
    tables.update(context.required_filters)
    report = check_sql(built.sql, _catalog(context, tables))
    if not report.ok:
        return None, built.sql, "; ".join(report.reasons)
    rows = run(built.sql)
    if not rows or not rows[0]:
        return None, built.sql, ""
    return _number(rows[0][0]), built.sql, ""


def _check_runs(
    recipe: Recipe,
    recipes: dict[str, Recipe],
    period: DateRange,
    context: BuildContext,
    run: Runner,
) -> tuple[RecipeCheck, dict[str, Decimal], str]:
    """Totals per side behind every later check, with the preview SQL."""
    try:
        sides = [recipe] if recipe.kind == "simple" else None
        if sides is None:
            numerator = recipes[recipe.numerator]
            denominator = recipes[recipe.denominator]
            if numerator.kind != "simple" or denominator.kind != "simple":
                return (
                    RecipeCheck(name="runs", passed=False, text="Ratios divide simple recipes."),
                    {},
                    "",
                )
            sides = [numerator, denominator]
        totals: dict[str, Decimal] = {}
        preview = ""
        roles = ["value"] if len(sides) == 1 else ["num", "den"]
        for role, side in zip(roles, sides, strict=True):
            value, sql, refusal = _run_total(side, recipes, period, context, run)
            preview = preview or sql
            if refusal:
                return (
                    RecipeCheck(name="runs", passed=False, text=f"The query is refused: {refusal}"),
                    {},
                    preview,
                )
            if value is None:
                return (
                    RecipeCheck(
                        name="runs", passed=False, text="The query ran but returned no number."
                    ),
                    {},
                    preview,
                )
            totals[role] = value
        return RecipeCheck(name="runs", passed=True, text="The query runs."), totals, preview
    except (ValueError, KeyError) as err:
        return RecipeCheck(name="runs", passed=False, text=f"The recipe can't run: {err}."), {}, ""


def _check_believable(recipe: Recipe, totals: dict[str, Decimal]) -> RecipeCheck:
    """Unit-derived bounds: counts can't be negative, shares stay 0-100."""
    if recipe.unit in ("count",):
        bad = [role for role, value in totals.items() if value < 0]
        if bad:
            return RecipeCheck(name="believable", passed=False, text="A count came back negative.")
        return RecipeCheck(name="believable", passed=True, text="Counts are not negative.")
    if recipe.unit == "percent":
        bad = [role for role, value in totals.items() if value < 0 or value > 100]
        if bad:
            return RecipeCheck(
                name="believable", passed=False, text="A share falls outside 0 to 100."
            )
        return RecipeCheck(name="believable", passed=True, text="Shares stay between 0 and 100.")
    return RecipeCheck(
        name="believable",
        passed=True,
        text="Money can be negative (refunds exist); the documents decide.",
    )


def _matching_numbers(recipe: Recipe, key: str, reported: list[ParsedNumber]) -> list[ParsedNumber]:
    """Reported numbers for this metric, unit and only this metric's words."""
    wanted = _words(recipe.title or key)
    matched = []
    for number in reported:
        if number.unit != recipe.unit:
            continue
        said = _words(number.text)
        if wanted and not wanted.issubset(said):
            continue
        matched.append(number)
    return matched


def _check_documents(
    recipe: Recipe,
    key: str,
    recipes: dict[str, Recipe],
    context: BuildContext,
    run: Runner,
    reported: list[ParsedNumber],
) -> tuple[RecipeCheck, list[ReportedCheck]]:
    """Each comparable document number must match at its written precision."""
    matched = _matching_numbers(recipe, key, reported)
    if not matched:
        return (
            RecipeCheck(
                name="matches_documents",
                passed=None,
                text="No document states this number for a matching period.",
            ),
            [],
        )
    checked: list[ReportedCheck] = []
    for number in matched:
        period = DateRange(start=number.start, end=number.end)
        try:
            kind = "ratio" if recipe.kind == "ratio" else "simple"
            if kind == "ratio":
                num = _run_total(recipes[recipe.numerator], recipes, period, context, run)
                den = _run_total(recipes[recipe.denominator], recipes, period, context, run)
                if num[2] or den[2] or num[0] is None:
                    return (
                        RecipeCheck(
                            name="matches_documents",
                            passed=False,
                            text="The document period can't be checked.",
                        ),
                        checked,
                    )
                got: Decimal | None = num[0] / den[0] if den[0] != 0 else None
                if recipe.unit == "percent" and got is not None:
                    got = got * 100
            else:
                got, _, refusal = _run_total(recipe, recipes, period, context, run)
                if refusal or got is None:
                    return (
                        RecipeCheck(
                            name="matches_documents",
                            passed=False,
                            text="The document period can't be checked.",
                        ),
                        checked,
                    )
            tolerance = Decimal(1).scaleb(-number.places) / 2
            if got is not None and abs(got - number.amount) <= tolerance:
                checked.append(
                    ReportedCheck(
                        fact_id=number.fact_id,
                        number_text=number.text,
                        period_start=number.start,
                        period_end=number.end,
                    )
                )
            else:
                return (
                    RecipeCheck(
                        name="matches_documents",
                        passed=False,
                        text=f"The documents say {number.amount} but the data says {got}.",
                    ),
                    checked,
                )
        except (ValueError, KeyError, ArithmeticError) as err:
            return (
                RecipeCheck(
                    name="matches_documents",
                    passed=False,
                    text=f"The document check failed: {err}.",
                ),
                checked,
            )
    return (
        RecipeCheck(
            name="matches_documents",
            passed=True,
            text=f"{len(checked)} document number(s) match at their written precision.",
        ),
        checked,
    )


def _side_parts(
    side: Recipe,
    side_key: str,
    recipes: dict[str, Recipe],
    period: DateRange,
    context: BuildContext,
    run: Runner,
) -> tuple[Decimal | None, str]:
    """Split sums against the side total; overlap is not applicable."""
    total, _, refusal = _run_total(side, recipes, period, context, run)
    if refusal or total is None:
        return None, refusal or "the side returned no number"
    for dimension in side.dimensions:
        built = build_query(
            "check",
            {**recipes, "check": side},
            QueryRequest(period=period, dimensions=[dimension.key]),
            context,
        )
        if built.overlapping_dimension is not None:
            return None, f"overlapping splits don't add up by design ({dimension.key})"
        tables = {side.table, dimension.table} if dimension.table else {side.table}
        tables.update(context.required_filters)
        report = check_sql(built.sql, _catalog(context, tables))
        if not report.ok:
            return None, "; ".join(report.reasons)
        rows = run(built.sql)
        parts = sum((_number(row[-1]) or 0) for row in rows)
        if parts != total:
            return None, f"split by {dimension.key}: parts add to {parts}, total is {total}"
    return total, ""


def _check_parts(
    recipe: Recipe,
    key: str,
    recipes: dict[str, Recipe],
    period: DateRange,
    context: BuildContext,
    run: Runner,
) -> RecipeCheck:
    """Splits add up; ratios check each side's inputs, never group ratios."""
    if recipe.kind == "ratio":
        try:
            sides = [recipes[recipe.numerator], recipes[recipe.denominator]]
        except KeyError as err:
            return RecipeCheck(
                name="parts_add_up", passed=False, text=f"The ratio names an unknown side: {err}."
            )
        for side in sides:
            _, problem = _side_parts(side, key, recipes, period, context, run)
            if problem and "don't add up by design" in problem:
                return RecipeCheck(name="parts_add_up", passed=None, text=problem)
            if problem:
                return RecipeCheck(name="parts_add_up", passed=False, text=problem)
        return RecipeCheck(
            name="parts_add_up", passed=True, text="Each side's splits add up to its total."
        )
    _, problem = _side_parts(recipe, key, recipes, period, context, run)
    if problem and "don't add up by design" in problem:
        return RecipeCheck(name="parts_add_up", passed=None, text=problem)
    if problem:
        return RecipeCheck(name="parts_add_up", passed=False, text=problem)
    return RecipeCheck(name="parts_add_up", passed=True, text="The splits add up to the total.")


def test_recipe(
    recipe: Recipe,
    key: str,
    recipes: dict[str, Recipe],
    period: DateRange,
    context: BuildContext,
    run: Runner,
    reported: list[ParsedNumber] | None = None,
) -> tuple[list[RecipeCheck], list[ReportedCheck], str]:
    """Run the four checks; returns checks, document matches and preview SQL."""
    reported = reported if reported is not None else []
    runs, totals, preview = _check_runs(recipe, recipes, period, context, run)
    if not runs.passed:
        skipped = [
            RecipeCheck(name=name, passed=None, text="The query didn't run.")
            for name in ("believable", "matches_documents", "parts_add_up")
        ]
        return [runs, *skipped], [], preview
    believable = _check_believable(recipe, totals)
    documents, matched = _check_documents(recipe, key, recipes, context, run, reported)
    parts = _check_parts(recipe, key, recipes, period, context, run)
    return [runs, believable, documents, parts], matched, preview
