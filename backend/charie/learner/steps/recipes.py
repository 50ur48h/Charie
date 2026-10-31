"""Step 8, recipes: propose and test one recipe per business number (P09.3c).

The AI names only non-code fields; code fills in joins, the time column
type, the checks, the SQL preview and the test date, then runs the four
checks. Simple metrics resolve before ratios, ratios only divide tested
simple recipes, and cycles are refused. Failures stay explicit: the entry
keeps its failed checks, the run records recipe failures for owner
questions, and automatic repair stops after two attempts per term.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from charie.learner.steps.base import StepContext, run_query
from charie.shared.ai.client import get_ai
from charie.shared.knowledge.keys import data_range_key, slug
from charie.shared.knowledge.query_builder import DateRange, load_build_context
from charie.shared.knowledge.recipe import (
    Recipe,
    RecipeCheck,
    RecipeDimension,
    RecipeError,
    ReportedCheck,
    check_fragment,
)
from charie.shared.knowledge.recipe_tests import (
    ParsedNumber,
    parse_reported_numbers,
    test_recipe,
)
from charie.shared.knowledge.store import get_entry, list_entries, upsert_entry
from charie.shared.settings import get_setting
from charie.shared.tables.sources import DocFact

JOB_KIND = "write_term_recipe"

REASON_RECIPE = "Proposed from learned evidence; checks decide if it can be trusted"
SOURCE_RECIPE = {"type": "ai", "text": REASON_RECIPE}

MAX_RECIPES = 25
MAX_REPAIRS = 2
MAX_EVIDENCE_SOURCES = 12


class RecipeProposal(BaseModel):
    """One recipe in the AI's words; code owns everything checkable."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(description="The proposal key this recipe is for.")
    kind: str = Field(description="simple or ratio.")
    title: str = Field(default="", description="The number's name; the term name when empty.")
    table: str = Field(default="", description="Its own table as schema.table; empty for ratios.")
    aggregate: str = Field(
        default="", description="sum, count or count_distinct; empty for ratios."
    )
    expression: str = Field(default="", description="What to add up or count; empty for ratios.")
    filters: list[str] = Field(default=[], description="Plain row filters; empty for ratios.")
    time_column: str = Field(default="", description="Its date column as table.column.")
    unit: str = Field(default="", description="money, count, percent or ratio.")
    currency: str = Field(default="", description="Three-letter code for money, else empty.")
    steps_in_words: list[str] = Field(default=[], description="Two to six plain steps.")
    numerator_key: str = Field(default="", description="The numerator term key; ratios only.")
    denominator_key: str = Field(default="", description="The denominator term key; ratios only.")
    dimensions: list[str] = Field(default=[], description="Split keys from the term's splits.")


class RecipeProposalForm(BaseModel):
    """The fixed form the recipe job answers in."""

    model_config = ConfigDict(extra="forbid")

    recipes: list[RecipeProposal] = Field(
        default=[], description="One recipe per term, most critical first."
    )


class ProposalError(ValueError):
    """A proposal code can't trust, in plain English."""


def _proposal_key(proposal: dict) -> str:
    return str(proposal.get("key") or "")


def _metric_key(name: str) -> str:
    return f"metric.{slug(name)}"


def _learned_tables(session, version_id: int) -> dict[str, str]:
    """Full table name by lowercase bare name; ambiguous bare names are dropped."""
    by_bare: dict[str, set[str]] = {}
    for entry in list_entries(session, version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        schema, name = details.get("schema") or "", details.get("name") or ""
        if schema and name:
            by_bare.setdefault(name.lower(), set()).add(f"{schema}.{name}")
    return {bare: next(iter(full)) for bare, full in by_bare.items() if len(full) == 1}


def _learned_columns(session, version_id: int) -> dict[str, dict]:
    """Column rows by full dotted name, with types."""
    known = {}
    for entry in list_entries(session, version_id, kinds=["column"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        schema = details.get("schema") or ""
        table, name = details.get("table") or "", details.get("name") or ""
        if schema and table and name:
            known[f"{schema}.{table}.{name}"] = {
                "type": details.get("data_type") or "",
                "table": f"{schema}.{table}",
            }
    return known


def _resolve_bare(bare: str, tables: dict[str, str]) -> str:
    try:
        return tables[bare.lower()]
    except KeyError:
        raise ProposalError(f"Unknown table `{bare}`.") from None


def _column_type(full_table: str, bare_column: str, columns: dict[str, dict]) -> str:
    matches = [
        full
        for full, row in columns.items()
        if full.lower() == f"{full_table}.{bare_column}".lower()
    ]
    if not matches:
        raise ProposalError(f"Unknown column `{bare_column}` on {full_table}.")
    dtype = (columns[matches[0]].get("type") or "").lower()
    if "timestamptz" in dtype:
        return "timestamptz"
    if "timestamp" in dtype:
        return "timestamp"
    if "date" in dtype:
        return "date"
    raise ProposalError(f"Column `{bare_column}` is not a date column.")


def _check_pieces(
    expression: str,
    filters: list[str],
    time_column: str,
    tables: dict[str, str],
    columns: dict[str, dict],
) -> None:
    """Every fragment reads known tables and names learned columns."""
    pieces = {"expression": expression, "time_column": time_column}
    for index, raw in enumerate(filters):
        pieces[f"filter {index + 1}"] = raw
    known = [full.lower() for full in columns]
    for name, raw in pieces.items():
        try:
            info = check_fragment(raw)
        except RecipeError as err:
            raise ProposalError(f"The {name} is unusable: {err}") from err
        for bare in info.tables:
            _resolve_bare(bare, tables)
        for dotted in info.columns:
            if not any(full.endswith(f".{dotted}".lower()) for full in known):
                raise ProposalError(f"The {name} names an unknown column `{dotted}`.")


def _dimension_details(session, version_id: int) -> dict[str, dict]:
    """Checked split entries by key."""
    found = {}
    for entry in list_entries(session, version_id, kinds=["dimension"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("kind") in ("attribute", "time"):
            found[entry.key] = details
    return found


def _recipe_dimensions(
    keys: list[str], allowed: list[str], dimensions: dict[str, dict]
) -> list[RecipeDimension]:
    """Split keys the term earned, as builder dimensions."""
    built = []
    for key in keys:
        if key not in allowed:
            raise ProposalError(f"Split `{key}` is not one of the term's splits.")
        details = dimensions.get(key)
        if details is None:
            raise ProposalError(f"Split `{key}` was never checked.")
        table = details.get("table") or ""
        column = details.get("column") or ""
        if not table or not column:
            raise ProposalError(f"Split `{key}` names no learned column.")
        bare = table.split(".")[-1]
        label = details.get("label_column") or ""
        built.append(
            RecipeDimension(
                key=key,
                kind=details.get("kind") or "attribute",
                table=table,
                expression=f"{bare}.{column}",
                label_expression=f"{bare}.{label}" if label else "",
                grain=details.get("grain"),
            )
        )
    return built


def assemble_simple(
    candidate: RecipeProposal,
    term: dict,
    tables: dict[str, str],
    columns: dict[str, dict],
    dimensions: dict[str, dict],
) -> Recipe:
    """A proposed simple recipe with code-owned fields filled in."""
    if candidate.kind != "simple":
        raise ProposalError("Only simple recipes use a table.")
    if not candidate.table:
        raise ProposalError("Simple recipes need their own table.")
    full_table = _resolve_bare(candidate.table.split(".")[-1], tables)
    if candidate.aggregate not in ("sum", "count", "count_distinct"):
        raise ProposalError(f"Unknown aggregate `{candidate.aggregate or 'empty'}`.")
    _check_pieces(candidate.expression, candidate.filters, candidate.time_column, tables, columns)
    time_bare = candidate.time_column.split(".")[-1]
    if candidate.time_column:
        if not candidate.time_column.startswith(full_table.split(".")[-1] + "."):
            raise ProposalError(f"The time column must come from {full_table}.")
        _resolve_bare(candidate.time_column.rsplit(".", 1)[0].split(".")[-1], tables)
    time_type = _column_type(full_table, time_bare, columns)
    allowed = term.get("dimensions") or []
    recipe_dimensions = _recipe_dimensions(candidate.dimensions, allowed, dimensions)
    try:
        return Recipe(
            kind="simple",
            title=(candidate.title or term.get("name") or "").strip(),
            table=full_table,
            aggregate=candidate.aggregate,  # type: ignore[arg-type]
            expression=candidate.expression.strip(),
            filters=list(candidate.filters),
            time_column=f"{full_table.split('.')[-1]}.{time_bare}",
            time_column_type=time_type,  # type: ignore[arg-type]
            unit=candidate.unit or term.get("unit") or "count",  # type: ignore[arg-type]
            currency=candidate.currency,
            steps_in_words=[step.strip() for step in candidate.steps_in_words if step.strip()],
            dimensions=recipe_dimensions,
        )
    except ValueError as err:
        raise ProposalError(f"The recipe is incomplete: {err}") from err


def assemble_ratio(
    candidate: RecipeProposal,
    term: dict,
    tested: dict[str, tuple[str, Recipe]],
) -> Recipe:
    """A ratio over two tested simple recipes; anything else is refused."""
    if candidate.kind != "ratio":
        raise ProposalError("Only ratios divide two recipes.")
    own = _metric_key(term.get("name") or _proposal_key(term))
    resolved = {}
    for role, term_key in (
        ("numerator", candidate.numerator_key),
        ("denominator", candidate.denominator_key),
    ):
        if not term_key:
            raise ProposalError(f"Ratios need a {role}.")
        found = tested.get(term_key)
        if found is None:
            raise ProposalError(f"The {role} `{term_key}` is not a tested recipe.")
        metric_key, side = found
        if side.kind != "simple":
            raise ProposalError("Ratios divide simple recipes, not other ratios.")
        if metric_key == own:
            raise ProposalError("A ratio can't divide a recipe by itself.")
        resolved[role] = metric_key
    if resolved["numerator"] == resolved["denominator"]:
        raise ProposalError("A ratio can't divide a recipe by itself.")
    try:
        return Recipe(
            kind="ratio",
            title=(candidate.title or term.get("name") or "").strip(),
            numerator=resolved["numerator"],
            denominator=resolved["denominator"],
            unit=candidate.unit or term.get("unit") or "ratio",  # type: ignore[arg-type]
            currency=candidate.currency,
            steps_in_words=[step.strip() for step in candidate.steps_in_words if step.strip()],
            dimensions=[],
        )
    except ValueError as err:
        raise ProposalError(f"The recipe is incomplete: {err}") from err


def build_recipe_input(session, version_id: int, proposals: list[dict]) -> dict:
    """Everything the recipe proposer gets: terms, columns and earned splits."""
    columns = _learned_columns(session, version_id)
    by_key = {_proposal_key(proposal): proposal for proposal in proposals}
    return {
        "terms": [
            {
                "key": key,
                "name": proposal.get("name") or "",
                "meaning": proposal.get("meaning") or "",
                "unit": proposal.get("unit") or "",
            }
            for key, proposal in sorted(by_key.items())
        ],
        "columns": [
            {"name": name, "type": row.get("type") or ""} for name, row in sorted(columns.items())
        ],
        "splits": [
            {"term": key, "key": dim}
            for key, proposal in sorted(by_key.items())
            for dim in (proposal.get("dimensions") or [])
        ],
    }


def _table_period(session, version_id: int, full_table: str) -> DateRange | None:
    """The learned date range for one table, or None without evidence."""
    schema, _, name = full_table.partition(".")
    entry = get_entry(session, version_id, data_range_key(schema, name))
    if entry is None or not isinstance(entry.details, dict):
        return None
    first, last = entry.details.get("date_from") or "", entry.details.get("date_to") or ""
    if not first or not last:
        return None
    return DateRange(start=first[:10], end=last[:10])


def _usable(checks: list[RecipeCheck]) -> bool:
    return all(check.passed is not False for check in checks) and any(
        check.name == "runs" and check.passed for check in checks
    )


def _save_recipe(
    ctx: StepContext,
    term: dict,
    recipe: Recipe,
    checks: list[RecipeCheck],
    reported: list[ReportedCheck],
    preview: str,
) -> str:
    """Store the checked recipe; only clean ones count as trusted."""
    key = _metric_key(term.get("name") or _proposal_key(term))
    confidence = "checked" if _usable(checks) else "guessed"
    sources = [dict(SOURCE_RECIPE)]
    for reference in (term.get("evidence") or [])[:MAX_EVIDENCE_SOURCES]:
        cleaned = str(reference).strip()
        if cleaned:
            sources.append({"type": "ai", "text": cleaned})
    upsert_entry(
        ctx.session,
        ctx.version_id,
        key,
        "metric",
        recipe.title or term.get("name") or key,
        term.get("meaning") or "",
        {
            **recipe.model_dump(),
            "tests": [check.model_dump() for check in checks],
            "reported_checks": [match.model_dump() for match in reported],
            "sql_preview": preview,
            "tested_at": datetime.now(UTC).isoformat(),
        },
        confidence,
        sources,
        REASON_RECIPE,
    )
    return key


def _reported(session, version_id: int) -> list[ParsedNumber]:
    """Reported numbers from ok document facts, oldest first."""
    facts = session.scalars(
        select(DocFact).where(DocFact.status == "ok").order_by(DocFact.id)
    ).all()
    rows = [
        {"fact_id": str(fact.id), "topic": fact.topic, "statement": fact.statement}
        for fact in facts
        if fact.kind == "reported_number"
    ]
    return parse_reported_numbers(rows)


def _test_and_save(
    ctx: StepContext,
    term: dict,
    recipe: Recipe,
    recipes: dict[str, Recipe],
    period: DateRange | None,
    reported: list[ParsedNumber],
) -> tuple[str, list[str]]:
    """Check one recipe, save it, and name any failure reasons."""
    key = _metric_key(term.get("name") or _proposal_key(term))
    if period is None:
        checks = [RecipeCheck(name="runs", passed=None, text="No learned date range to test on.")]
        _save_recipe(ctx, term, recipe, checks, [], "")
        return key, ["no learned date range"]
    checks, matched, preview = test_recipe(
        recipe,
        key,
        recipes,
        period,
        load_build_context(ctx.session, ctx.version_id, get_setting(ctx.session, "time_zone")),
        lambda sql: run_query(ctx, "recipe_test", sql).rows,
        reported,
    )
    _save_recipe(ctx, term, recipe, checks, matched, preview)
    failed = [check.name for check in checks if check.passed is False]
    return key, [f"{name}: {next(c.text for c in checks if c.name == name)}" for name in failed]


def propose_recipes(
    ctx: StepContext, proposals: list[dict], repair: str = ""
) -> dict[str, RecipeProposal]:
    """Ask the AI for one recipe per term; unknowns and duplicates are left out."""
    form = get_ai().run(
        JOB_KIND,
        {**build_recipe_input(ctx.session, ctx.version_id, proposals), "repair": repair},
        RecipeProposalForm,
        app="learner",
        learning_run_id=ctx.run_id,
    )
    by_term = {_proposal_key(proposal): proposal for proposal in proposals}
    candidates: dict[str, RecipeProposal] = {}
    warnings: dict[str, str] = {}
    for candidate in form.recipes[:MAX_RECIPES]:
        if candidate.term not in by_term:
            ctx.say("warning", f"I left out a recipe for an unknown term: {candidate.term}.")
            continue
        if candidate.term in candidates:
            ctx.say(
                "warning", f"I kept the first recipe for {candidate.term} and left out the rest."
            )
            continue
        candidates[candidate.term] = candidate
    if len(form.recipes) > MAX_RECIPES:
        ctx.say("warning", f"I kept the first {MAX_RECIPES} recipes and left out the rest.")
    return candidates, warnings


def discover_and_test(ctx: StepContext, proposals: list[dict]) -> tuple[int, list[dict]]:
    """Propose, assemble (simple first), test, repair twice, save; returns kept and failures."""
    by_term = {_proposal_key(proposal): proposal for proposal in proposals}
    tables = _learned_tables(ctx.session, ctx.version_id)
    columns = _learned_columns(ctx.session, ctx.version_id)
    dimensions = _dimension_details(ctx.session, ctx.version_id)
    reported = _reported(ctx.session, ctx.version_id)
    failures: dict[str, list[str]] = {}
    attempts: dict[str, int] = {}
    pending = dict(by_term)
    recipes: dict[str, Recipe] = {}
    tested: dict[str, tuple[str, Recipe]] = {}
    repair_notes: dict[str, str] = {}
    while pending:
        candidates, _ = propose_recipes(
            ctx,
            [by_term[key] for key in sorted(pending)],
            repair="; ".join(f"{key}: {note}" for key, note in sorted(repair_notes.items())),
        )
        repair_notes = {}
        for term_key, candidate in sorted(candidates.items()):
            term = by_term.get(term_key)
            if term is None or term_key not in pending:
                continue
            try:
                if candidate.kind == "ratio":
                    recipe = assemble_ratio(candidate, term, tested)
                else:
                    recipe = assemble_simple(candidate, term, tables, columns, dimensions)
            except (ProposalError, ValueError) as err:
                failures.setdefault(term_key, []).append(str(err))
                attempts[term_key] = attempts.get(term_key, 0) + 1
                if attempts[term_key] <= MAX_REPAIRS:
                    repair_notes[term_key] = str(err)
                    continue
                ctx.say("warning", f"I couldn't write a recipe for {term_key}: {err}")
                del pending[term_key]
                continue
            metric_key = _metric_key(term.get("name") or term_key)
            trial = dict(recipes)
            trial[metric_key] = recipe
            period = None
            if recipe.kind == "simple":
                period = _table_period(ctx.session, ctx.version_id, recipe.table)
            else:
                period = _table_period(ctx.session, ctx.version_id, trial[recipe.numerator].table)
            key, problems = _test_and_save(ctx, term, recipe, trial, period, reported)
            if problems:
                failures.setdefault(term_key, []).extend(problems)
                attempts[term_key] = attempts.get(term_key, 0) + 1
                if attempts[term_key] <= MAX_REPAIRS:
                    repair_notes[term_key] = "; ".join(problems)
                    continue
                ctx.say("warning", f"The recipe for {term_key} failed its checks; asking you.")
            else:
                recipes[metric_key] = recipe
                if recipe.kind == "simple":
                    tested[term_key] = (metric_key, recipe)
            del pending[term_key]
        for term_key in [
            key for key in pending if key not in candidates and key not in repair_notes
        ]:
            failures.setdefault(term_key, []).append("the AI proposed no recipe")
            attempts[term_key] = attempts.get(term_key, 0) + 1
            if attempts[term_key] <= MAX_REPAIRS:
                repair_notes[term_key] = "no recipe proposed; propose one"
            else:
                ctx.say("warning", f"I couldn't write a recipe for {term_key}; asking you.")
                del pending[term_key]
        if not repair_notes:
            break
    kept = len(recipes)
    ctx.say("found", f"Kept {kept} tested recipe(s); failures stay explicit for your questions.")
    return kept, [
        {"term": term_key, "reasons": reasons} for term_key, reasons in sorted(failures.items())
    ]


def failed_recipes(session, version_id: int) -> list[dict]:
    """Metric entries with a failed check, for owner questions (P09.5)."""
    found = []
    for entry in list_entries(session, version_id, kinds=["metric"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        failed = [
            check.get("name")
            for check in details.get("tests") or []
            if isinstance(check, dict) and check.get("passed") is False
        ]
        if failed:
            found.append({"key": entry.key, "title": entry.title, "failed": failed})
    return sorted(found, key=lambda row: row["key"])


def _recipe_dependents(recipe: Recipe) -> set[str]:
    """Everything a recipe reads: tables, columns, rules and sides."""
    touched = {recipe.table} if recipe.table else set()
    for raw in [recipe.expression, recipe.time_column, *recipe.filters]:
        if not raw or raw.strip() == "*":
            continue
        try:
            info = check_fragment(raw)
        except RecipeError:
            continue
        touched.update(info.tables)
        touched.update(info.columns)
    for dimension in recipe.dimensions:
        if dimension.table:
            touched.add(dimension.table)
    if recipe.kind == "ratio":
        touched.update({recipe.numerator, recipe.denominator})
    return {touch for touch in touched if touch}


def retest_affected(session, version_id: int, keys: list[str], run) -> dict[str, bool]:
    """Retest recipes touching any key once; unrelated recipes are not rerun."""
    wanted = set(keys)
    entries = [
        entry
        for entry in list_entries(session, version_id, kinds=["metric"])
        if isinstance(entry.details, dict)
    ]
    recipes = {}
    for entry in entries:
        try:
            recipes[entry.key] = Recipe.model_validate(entry.details)
        except ValueError:
            continue
    time_zone = get_setting(session, "time_zone") or "UTC"
    context = load_build_context(session, version_id, time_zone)
    facts = session.scalars(
        select(DocFact).where(DocFact.status == "ok").order_by(DocFact.id)
    ).all()
    reported = parse_reported_numbers(
        [
            {"fact_id": str(fact.id), "topic": fact.topic, "statement": fact.statement}
            for fact in facts
            if fact.kind == "reported_number"
        ]
    )
    outcome: dict[str, bool] = {}
    for key, recipe in sorted(recipes.items()):
        touched = _recipe_dependents(recipe)
        if not any(
            want == touch or want.endswith(f".{touch}") or touch == want.split(".")[-1]
            for want in wanted
            for touch in touched
        ):
            continue
        table = recipe.table or recipes.get(recipe.numerator, recipe).table
        period = _table_period(session, version_id, table)
        if period is None:
            outcome[key] = False
            continue
        checks, matched, preview = test_recipe(recipe, key, recipes, period, context, run, reported)
        entry = get_entry(session, version_id, key)
        if entry is None:
            continue
        details = dict(entry.details) if isinstance(entry.details, dict) else {}
        details.update(
            {
                "tests": [check.model_dump() for check in checks],
                "reported_checks": [match.model_dump() for match in matched],
                "sql_preview": preview,
                "tested_at": datetime.now(UTC).isoformat(),
            }
        )
        upsert_entry(
            session,
            version_id,
            key,
            "metric",
            entry.title,
            entry.meaning,
            details,
            "checked" if _usable(checks) else "guessed",
            entry.sources if isinstance(entry.sources, list) else [],
            "Retested after a change.",
        )
        outcome[key] = _usable(checks)
    return outcome
