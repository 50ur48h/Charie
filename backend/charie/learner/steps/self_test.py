"""Step 11, self-test: practice questions with an independent examiner (P09.8).

Code maps each practice question to a tested metric, period and splits;
the AI only writes the question words. The recipe's own query and the
examiner's fresh query run read-only, and code compares them by
dimension ids. Disagreements mark the recipe untrusted so the next owner
questions run asks about it; the readiness report lands on the draft.
"""

import time
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from charie.learner.steps.base import (
    Step,
    StepContext,
    register_step,
    register_step_handler,
    run_query,
)
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import AiError, SpendingPaused
from charie.shared.connectors.base import ConnectorError
from charie.shared.knowledge.query_builder import (
    DateRange,
    QueryRequest,
    build_query,
    load_build_context,
)
from charie.shared.knowledge.recipe import Recipe
from charie.shared.knowledge.sql_writer import (
    ExaminerBlocked,
    ExamTask,
    compare_results,
    examiner_brief,
    tolerance_for,
    write_checked_sql,
)
from charie.shared.safety.sql_check import check_sql
from charie.shared.settings import get_setting
from charie.shared.tables.chat import QueryRun
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import OwnerQuestion
from charie.shared.tables.sources import DataSource

JOB_KIND = "write_practice_questions"
PRACTICE_JOB = JOB_KIND
STEP_NAME = "self_test"


class PracticeQuestionDraft(BaseModel):
    """One practice question in the AI's words; code checks the mapping."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(description="The practice question in plain words, no amounts.")
    metric: str = Field(description="The tested metric key, copied exactly.")
    period_start: str = Field(description="First day, like 2025-11-01.")
    period_end: str = Field(description="Last day, like 2025-11-30.")
    splits: list[str] = Field(default=[], description="Dimension keys, or empty.")


class PracticeQuestionsForm(BaseModel):
    """The fixed form the practice-question job answers in."""

    model_config = ConfigDict(extra="forbid")

    questions: list[PracticeQuestionDraft] = Field(
        default=[], description="Up to the requested count of practice questions."
    )


class ReadinessReport(BaseModel):
    """The step-5 report: counts, practice score and what still needs you."""

    model_config = ConfigDict(extra="forbid")

    numbers_checked: int = 0
    numbers_total: int = 0
    numbers_waiting: int = 0
    practice_right: int = 0
    practice_total: int = 0
    weak_area: str | None = None
    weak_area_why: str | None = None
    outcomes: list[dict] = Field(default=[])
    learned_at: str = ""
    data_through: str | None = None
    unchecked_metrics: list[str] = Field(default=[])
    pending_topics: list[str] = Field(default=[])


def _parse_day(raw: str):
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _metric_recipes(session, version_id: int) -> dict[str, Recipe]:
    """Every metric with a readable recipe."""
    from charie.shared.knowledge.store import list_entries

    recipes = {}
    for entry in list_entries(session, version_id, kinds=["metric"]):
        if not isinstance(entry.details, dict):
            continue
        try:
            recipes[entry.key] = Recipe.model_validate(entry.details)
        except ValueError:
            continue
    return recipes


def valid_mapping(session, version_id: int, draft: PracticeQuestionDraft) -> str | None:
    """Why this practice mapping can't run, or None when it can."""
    from charie.shared.knowledge.defaults import tested_metric_keys

    if draft.metric not in tested_metric_keys(session, version_id):
        return f"Unknown metric: {draft.metric}."
    recipes = _metric_recipes(session, version_id)
    recipe = recipes.get(draft.metric)
    if recipe is None or recipe.kind != "simple":
        return f"Unsupported metric: {draft.metric}."
    start, end = _parse_day(draft.period_start), _parse_day(draft.period_end)
    if start is None or end is None or start > end:
        return "The period is not a valid date range."
    known = {dimension.key: dimension for dimension in recipe.dimensions}
    for split in draft.splits:
        dimension = known.get(split)
        if dimension is None:
            return f"Unknown split: {split}."
        if dimension.kind == "time" and not dimension.grain:
            return f"Split {split} needs a time grain."
    return None


def _log_run(
    session,
    run_id: int | None,
    purpose: str,
    key: str,
    way: str,
    sql: str,
    report,
    status: str,
    rows: int,
    duration_ms: int,
    error: str | None,
) -> None:
    """One query_runs row for a self-test query, checked or blocked."""
    session.add(
        QueryRun(
            learning_run_id=run_id,
            purpose=purpose,
            recipe_key=key,
            way=way,
            sql_text=sql,
            check_report=report.model_dump() if report is not None else {},
            status=status,
            row_count=rows,
            duration_ms=duration_ms,
            error=error,
        )
    )
    session.flush()


def _project_value(columns: list[str], rows: list[list]) -> tuple[list[str], list[list]]:
    """Drop label columns; the value stays last."""
    keep = [position for position, name in enumerate(columns) if not name.endswith("_label")]
    kept = [columns[position] for position in keep]
    if kept and kept[-1] != columns[-1]:
        position = len(columns) - 1
        if position not in keep:
            keep.append(position)
            kept.append(columns[position])
    return kept, [[row[position] for position in keep] for row in rows]


def _run_table(run, sql: str):
    """Columns and rows from a read-only run."""
    result = run(sql)
    return list(result.columns), [list(row) for row in result.rows]


def practice_one(
    session,
    version_id: int,
    draft: PracticeQuestionDraft,
    run,
    time_zone: str,
    learning_run_id: int | None = None,
) -> dict:
    """Run both sides of one practice question and compare them."""

    recipes = _metric_recipes(session, version_id)
    recipe = recipes.get(draft.metric)
    if recipe is None or recipe.kind != "simple":
        return {
            "question": draft.question,
            "metric": draft.metric,
            "period": [draft.period_start, draft.period_end],
            "splits": list(draft.splits),
            "status": "unrun",
            "reason": f"Unsupported metric: {draft.metric}.",
            "tolerance": "0",
            "recipe_rows": 0,
            "examiner_rows": 0,
        }
    context = load_build_context(session, version_id, time_zone)
    period = DateRange(start=draft.period_start, end=draft.period_end)
    built = build_query(
        draft.metric,
        {draft.metric: recipe},
        QueryRequest(period=period, dimensions=list(draft.splits)),
        context,
    )
    started = time.monotonic()
    try:
        report = check_sql(built.sql, _checker_catalog(session, version_id, time_zone))
        if not report.ok:
            raise ExaminerBlocked(f"The recipe query is refused: {'; '.join(report.reasons)}")
        recipe_columns, recipe_rows = _run_table(run, report.sql)
        duration = int((time.monotonic() - started) * 1000)
        _log_run(
            session,
            learning_run_id,
            draft.question,
            draft.metric,
            "recipe",
            report.sql,
            report,
            "ok",
            len(recipe_rows),
            duration,
            None,
        )
        recipe_columns, recipe_rows = _project_value(recipe_columns, recipe_rows)
    except SpendingPaused:
        raise
    except (ExaminerBlocked, ConnectorError, Exception) as err:  # noqa: BLE001 (one bad side never fails the run)
        duration = int((time.monotonic() - started) * 1000)
        _log_run(
            session,
            learning_run_id,
            draft.question,
            draft.metric,
            "recipe",
            built.sql,
            None,
            "blocked" if isinstance(err, ExaminerBlocked) else "failed",
            0,
            duration,
            str(err),
        )
        return _outcome(draft, "unrun", f"The recipe side can't run: {err}.", 0, 0, recipe)
    task = ExamTask(
        question=draft.question,
        metric_key=draft.metric,
        period_start=draft.period_start,
        period_end=draft.period_end,
        splits=tuple(draft.splits),
        unit=recipe.unit,
        currency=recipe.currency,
    )
    started = time.monotonic()
    try:
        written = write_checked_sql(
            examiner_brief(session, version_id, task, time_zone), run, learning_run_id
        )
        duration = int((time.monotonic() - started) * 1000)
        _log_run(
            session,
            learning_run_id,
            draft.question,
            draft.metric,
            "examiner",
            written.sql,
            None,
            "ok",
            len(written.rows),
            duration,
            None,
        )
    except SpendingPaused:
        raise
    except (ExaminerBlocked, ConnectorError, Exception) as err:  # noqa: BLE001 (see above)
        duration = int((time.monotonic() - started) * 1000)
        _log_run(
            session,
            learning_run_id,
            draft.question,
            draft.metric,
            "examiner",
            task.question,
            None,
            "blocked" if isinstance(err, ExaminerBlocked) else "failed",
            0,
            duration,
            str(err),
        )
        return _outcome(
            draft, "unrun", f"The examiner can't run: {err}.", len(recipe_rows), 0, recipe
        )
    compared = compare_results(
        recipe_columns, recipe_rows, written.columns, written.rows, recipe.unit, recipe.currency
    )
    status = "match" if compared.match else "wrong"
    return _outcome(
        draft,
        status,
        compared.reason,
        len(recipe_rows),
        len(written.rows),
        recipe,
        tolerance=str(compared.tolerance),
    )


def _outcome(
    draft,
    status: str,
    reason: str,
    recipe_rows: int,
    examiner_rows: int,
    recipe: Recipe,
    tolerance: str = "",
) -> dict:
    return {
        "question": draft.question,
        "metric": draft.metric,
        "period": [draft.period_start, draft.period_end],
        "splits": list(draft.splits),
        "status": status,
        "reason": reason,
        "tolerance": tolerance or str(tolerance_for(recipe.unit, recipe.currency)),
        "recipe_rows": recipe_rows,
        "examiner_rows": examiner_rows,
    }


def _checker_catalog(session, version_id: int, time_zone: str):
    """The checker catalog for self-test queries: learned tables, tested links."""
    from charie.shared.knowledge.query_builder import load_build_context
    from charie.shared.safety.catalog import Catalog, Link, RequiredFilter

    context = load_build_context(session, version_id, time_zone)
    links = []
    for link in context.links:
        if not link.tested or link.from_table == link.to_table:
            continue
        links.append(
            Link(
                one_table=link.to_table,
                one_column=link.to_column,
                many_table=link.from_table,
                many_column=link.from_column,
            )
            if link.multiplicity == "many_to_one"
            else Link(
                one_table=link.from_table,
                one_column=link.from_column,
                many_table=link.to_table,
                many_column=link.to_column,
            )
        )
    tables = set(context.tables) | set(context.required_filters)
    return Catalog(
        tables=sorted(tables),
        forbidden_tables=list(context.forbidden_tables),
        required_filters=[
            RequiredFilter(table=table, sql=sql, reason="a hard rule")
            for table, sqls in context.required_filters.items()
            for sql in sqls
        ],
        links=links,
    )


def _recipe_usable(tests: list) -> bool:
    """No failed checks and a passing runs check, from stored test dicts."""
    runs_ok = any(
        isinstance(check, dict) and check.get("name") == "runs" and check.get("passed")
        for check in tests
    )
    return runs_ok and all(
        not isinstance(check, dict) or check.get("passed") is not False for check in tests
    )


def generate_questions(
    session, version_id: int, count: int, learning_run_id: int | None = None
) -> list[PracticeQuestionDraft]:
    """Ask the AI for practice mappings; code validates every one."""
    metrics = []
    recipes = _metric_recipes(session, version_id)
    for key in sorted(recipes):
        entry = _entry(session, version_id, key)
        metrics.append(
            {
                "key": key,
                "title": entry.title if entry is not None else key,
                "unit": recipes[key].unit,
                "dimensions": [dimension.key for dimension in recipes[key].dimensions],
            }
        )
    if not metrics:
        return []
    form = get_ai().run(
        PRACTICE_JOB,
        {"metrics": metrics, "count": count},
        PracticeQuestionsForm,
        app="learner",
        learning_run_id=learning_run_id,
    )
    return list(form.questions or [])


def _entry(session, version_id: int, key: str):
    from charie.shared.knowledge.store import get_entry

    return get_entry(session, version_id, key)


def _ours(ctx: StepContext) -> dict:
    run = ctx.session.get(LearningRun, ctx.run_id)
    return ((run.progress or {}).get(STEP_NAME) or {}) if run is not None else {}


def _save(ctx: StepContext, requested: int, outcomes: list[dict]) -> None:
    run = ctx.session.get(LearningRun, ctx.run_id)
    progress = dict(run.progress or {})
    progress[STEP_NAME] = {"requested": requested, "outcomes": outcomes}
    run.progress = progress
    flag_modified(run, "progress")
    ctx.session.flush()


def make_jobs(ctx: StepContext) -> list[dict]:
    """One self-test job while any tested metric exists."""
    if not _metric_recipes(ctx.session, ctx.version_id):
        return []
    return [{"step": STEP_NAME}]


def _requested(ctx: StepContext) -> int:
    """The validated practice-question count: 1 to 200, default 50."""
    try:
        count = int(get_setting(ctx.session, "self_test_question_count"))
    except (TypeError, ValueError):
        return 50
    if isinstance(count, bool):
        return 50
    return min(200, max(1, count))


def run_job(info, ctx: StepContext) -> None:
    """Generate, validate and run every practice question."""

    def run(sql: str):
        return run_query(ctx, "self_test", sql)

    if ctx.connector is None:
        ctx.say("warning", "No database connection, so the self-test can't run.")
        _save(ctx, 0, [])
        return
    requested = _requested(ctx)
    time_zone = get_setting(ctx.session, "time_zone") or "UTC"
    try:
        drafts = generate_questions(ctx.session, ctx.version_id, requested, ctx.run_id)
    except SpendingPaused:
        raise
    except Exception as err:  # noqa: BLE001 (the worker retries first; see below)
        if info.attempts >= 3:
            message = err.message if isinstance(err, AiError) else "Something went wrong."
            ctx.say("warning", f"Couldn't write practice questions: {message}")
            _save(ctx, requested, [])
            return
        raise
    outcomes = []
    for draft in drafts[:requested]:
        problem = valid_mapping(ctx.session, ctx.version_id, draft)
        if problem is not None:
            ctx.say("warning", f"Left out a practice question: {problem}")
            continue
        outcomes.append(
            practice_one(ctx.session, ctx.version_id, draft, run, time_zone, ctx.run_id)
        )
    _save(ctx, requested, outcomes)
    right = sum(1 for outcome in outcomes if outcome["status"] == "match")
    ctx.say("found", f"Checked {len(outcomes)} practice question(s); {right} agree.")


def finish_step(ctx: StepContext) -> None:
    """Store the readiness report and mark disagreements untrusted."""
    from charie.shared.knowledge.store import upsert_entry

    session = ctx.session
    outcomes = _ours(ctx).get("outcomes") or []
    recipes = _metric_recipes(session, ctx.version_id)
    usable = {}
    for key in recipes:
        entry = _entry(session, ctx.version_id, key)
        tests = entry.details.get("tests") if entry is not None else []
        usable[key] = _recipe_usable(tests if isinstance(tests, list) else [])
    waiting_metrics = set()
    waiting_topics = []
    for row in session.scalars(
        select(OwnerQuestion).where(OwnerQuestion.status == "waiting")
    ).all():
        waiting_topics.append(row.topic)
        waiting_metrics.update(
            key for key in (row.affects or []) if isinstance(key, str) and key in recipes
        )
    wrong_by_metric: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.get("status") != "wrong":
            continue
        key = outcome.get("metric") or ""
        wrong_by_metric[key] = wrong_by_metric.get(key, 0) + 1
        entry = _entry(session, ctx.version_id, key)
        if entry is None:
            continue
        details = dict(entry.details) if isinstance(entry.details, dict) else {}
        tests = list(details.get("tests") or [])
        tests.append({"name": "self_test", "passed": False, "text": outcome.get("reason") or ""})
        details["tests"] = tests
        sources = list(entry.sources) if isinstance(entry.sources, list) else []
        sources.append({"type": "ai", "text": "The self-test disagrees."})
        upsert_entry(
            session,
            ctx.version_id,
            key,
            entry.kind,
            entry.title,
            entry.meaning,
            details,
            "guessed",
            sources,
            "The self-test disagrees.",
        )
    right = sum(1 for outcome in outcomes if outcome.get("status") == "match")
    weak = sorted(wrong_by_metric, key=lambda key: (-wrong_by_metric[key], key))
    weak_key = weak[0] if weak else None
    weak_entry = _entry(session, ctx.version_id, weak_key) if weak_key else None
    source = session.scalar(select(DataSource).order_by(DataSource.id.desc()).limit(1))
    report = ReadinessReport(
        numbers_checked=sum(1 for key in recipes if usable.get(key)),
        numbers_total=len(recipes),
        numbers_waiting=len(waiting_metrics),
        practice_right=right,
        practice_total=len(outcomes),
        weak_area=weak_entry.title if weak_entry is not None else None,
        weak_area_why=(
            f"{weak_entry.title} disagrees on {wrong_by_metric[weak_key]} practice question(s)."
            if weak_entry is not None and weak_key is not None
            else "Charie did well everywhere."
        ),
        outcomes=outcomes,
        learned_at=datetime.now(UTC).isoformat(),
        data_through=source.data_through.isoformat()
        if source is not None and source.data_through
        else None,
        unchecked_metrics=sorted(key for key in recipes if not usable.get(key)),
        pending_topics=waiting_topics,
    )
    version = session.get(KbVersion, ctx.version_id)
    if version is not None:
        version.readiness = report.model_dump()
        session.flush()
    ctx.say(
        "found",
        f"Readiness: {report.numbers_checked} of {report.numbers_total} numbers checked, "
        f"{right} of {len(outcomes)} practice questions agree.",
    )


SELF_TEST_STEP = Step(
    name="self_test",
    title="Self-test",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="No tested metrics to check yet.",
)

register_step(SELF_TEST_STEP)
register_step_handler("self_test")
