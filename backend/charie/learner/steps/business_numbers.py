"""Step 8: propose business numbers from learned evidence (P09.3).

The AI names candidate terms; code keeps only what cites real evidence.
Proposals stay proposals (`proposed: true`) until P09.3c validates them,
so nothing unchecked can feed the analyst. A second run merges by stable
key instead of duplicating, and confirmed meanings are never overwritten.
"""

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
from charie.learner.steps.explain_tables import UnitKind
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import AiError, SpendingPaused
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge.dimensions import infer_unique_with
from charie.shared.knowledge.keys import slug
from charie.shared.knowledge.query_builder import load_build_context
from charie.shared.knowledge.recipe import DimensionDetails
from charie.shared.knowledge.store import get_entry, list_entries, upsert_entry
from charie.shared.settings import get_setting
from charie.shared.tables.learning import Job, LearningRun
from charie.shared.tables.sources import DocFact

JOB_KIND = "find_business_terms"
FIND_DIMENSIONS_JOB = "find_dimensions"

STEP_NAME = "business_numbers"

REASON_PROPOSED = "Proposed from learned evidence; unchecked until recipe tests pass"
REASON_DIMENSION = "Split checked against learned columns and uniqueness reads"
SOURCE_DIMENSION = {"type": "ai", "text": REASON_DIMENSION}

MAX_TERMS = 25
MAX_SPLITS = 5
MAX_EVIDENCE = 8
MAX_DOC_FACTS = 200
MAX_DIMENSIONS = 50

GRAINS = ("day", "week", "month", "quarter", "year")
DATE_TYPES = ("date", "time", "timestamp")


class TermCandidate(BaseModel):
    """One business number the evidence supports, in the AI's words."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="The term the way the business says it.")
    meaning: str = Field(description="What the number means, in one plain sentence.")
    unit: UnitKind = Field(description="What the number measures.")
    evidence: list[str] = Field(
        default=[],
        description="Source references: table:, column:, doc: or rule: entries.",
    )
    splits: list[str] = Field(default=[], description="How the business may want the number split.")


class DiscoverTermsForm(BaseModel):
    """The fixed form the discovery job answers in."""

    model_config = ConfigDict(extra="forbid")

    terms: list[TermCandidate] = Field(
        default=[], description="The candidate business numbers, most critical first."
    )


def _tables(session, version_id: int) -> list[dict]:
    """Table names and meanings the structure step learned."""
    rows = []
    for entry in list_entries(session, version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        schema, name = details.get("schema") or "", details.get("name") or ""
        if not schema or not name:
            continue
        rows.append(
            {
                "name": f"{schema}.{name}",
                "meaning": entry.meaning or "",
                "grain": details.get("grain") or "",
            }
        )
    rows.sort(key=lambda row: row["name"])
    return rows


def _columns(session, version_id: int) -> list[dict]:
    """Column names, meanings and units the explanation step checked."""
    rows = []
    for entry in list_entries(session, version_id, kinds=["column"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        schema = details.get("schema") or ""
        table, name = details.get("table") or "", details.get("name") or ""
        if not schema or not table or not name:
            continue
        rows.append(
            {
                "name": f"{schema}.{table}.{name}",
                "meaning": entry.meaning or "",
                "unit": details.get("unit") or "",
                "type": details.get("data_type") or "",
            }
        )
    rows.sort(key=lambda row: row["name"])
    return rows


def _rules(session, version_id: int) -> list[dict]:
    """Owner rules, by title."""
    rows = []
    for entry in list_entries(session, version_id, kinds=["rule"]):
        rows.append({"title": entry.title or "", "meaning": entry.meaning or ""})
    rows.sort(key=lambda row: row["title"])
    return rows


def _doc_facts(session) -> list[dict]:
    """Verified document facts: topic and statement, oldest first."""
    facts = session.scalars(
        select(DocFact).where(DocFact.status == "ok").order_by(DocFact.id)
    ).all()
    return [
        {"topic": fact.topic or "", "statement": fact.statement or ""}
        for fact in facts[:MAX_DOC_FACTS]
    ]


def build_discover_input(session, version_id: int) -> dict:
    """Everything the AI gets: meanings, rules and verified facts."""
    return {
        "tables": _tables(session, version_id),
        "columns": _columns(session, version_id),
        "rules": _rules(session, version_id),
        "doc_facts": _doc_facts(session),
    }


def _known_evidence(session, version_id: int) -> set[str]:
    """Every evidence reference the AI may cite."""
    known = set()
    for row in _tables(session, version_id):
        known.add(f"table:{row['name']}")
    for row in _columns(session, version_id):
        known.add(f"column:{row['name']}")
    for fact in _doc_facts(session):
        if fact["topic"].strip():
            known.add(f"doc:{fact['topic'].strip()}")
    for row in _rules(session, version_id):
        if row["title"].strip():
            known.add(f"rule:{row['title'].strip()}")
    return known


def _merge(merged: dict[str, dict], term: TermCandidate) -> None:
    """Add or merge one candidate by stable key, keeping the bounds."""
    key = f"term.{slug(term.name)}"
    if key not in merged:
        merged[key] = {
            "key": key,
            "name": term.name.strip(),
            "meaning": term.meaning.strip(),
            "unit": term.unit,
            "splits": [],
            "evidence": [],
            "proposed": True,
        }
    current = merged[key]
    for split in term.splits:
        cleaned = split.strip()
        if cleaned and cleaned not in current["splits"] and len(current["splits"]) < MAX_SPLITS:
            current["splits"].append(cleaned)
    for reference in term.evidence:
        cleaned = reference.strip()
        if (
            cleaned
            and cleaned not in current["evidence"]
            and len(current["evidence"]) < MAX_EVIDENCE
        ):
            current["evidence"].append(cleaned)


def _ours(ctx: StepContext) -> dict:
    """This step's progress: proposals, dimensions and stage checkpoints."""
    progress = ctx.session.get(LearningRun, ctx.run_id).progress or {}
    return progress.get(STEP_NAME) or {}


def make_jobs(ctx: StepContext) -> list[dict]:
    """One discovery job until proposals, dimensions and recipes are all done."""
    ours = _ours(ctx)
    if ours.get("proposals") and ours.get("dimensions_done") and ours.get("recipes_done"):
        return []
    busy = {
        (job.payload or {}).get("step")
        for job in ctx.session.scalars(
            select(Job).where(Job.kind == JOB_KIND, Job.status.in_(("queued", "running")))
        )
    }
    if STEP_NAME in busy:
        return []
    return [{"step": STEP_NAME}]


def discover_terms(ctx: StepContext) -> list[dict]:
    """Ask the AI, keep only evidenced terms, merge them into proposals."""
    form = get_ai().run(
        JOB_KIND,
        build_discover_input(ctx.session, ctx.version_id),
        DiscoverTermsForm,
        app="learner",
        learning_run_id=ctx.run_id,
    )
    known = _known_evidence(ctx.session, ctx.version_id)
    merged: dict[str, dict] = {}
    dropped = 0
    for term in form.terms[:MAX_TERMS]:
        if not term.name.strip():
            dropped += 1
            continue
        if any(reference.strip() not in known for reference in term.evidence):
            dropped += 1
            continue
        _merge(merged, term)
    if len(form.terms) > MAX_TERMS:
        ctx.say("warning", f"I kept the first {MAX_TERMS} terms and left out the rest.")
    if dropped:
        ctx.say("warning", f"I left out {dropped} term(s) without real evidence.")
    return sorted(merged.values(), key=lambda proposal: proposal["key"])


class DimensionCandidate(BaseModel):
    """One split a term needs, in the AI's words."""

    model_config = ConfigDict(extra="forbid")

    term: str = Field(description="The proposal key this split belongs to.")
    table: str = Field(description="The table, as schema.table.")
    column: str = Field(description="The column to split by.")
    label_column: str = Field(
        default="", description="The readable column on the same table, or empty."
    )
    grain: str = Field(
        default="", description="day, week, month, quarter or year; empty unless time."
    )


class DimensionForm(BaseModel):
    """The fixed form the dimension job answers in."""

    model_config = ConfigDict(extra="forbid")

    dimensions: list[DimensionCandidate] = Field(
        default=[], description="The splits each term needs."
    )


def _known_columns(session, version_id: int) -> dict[tuple[str, str, str], dict]:
    """Learned columns by (schema, table, column), with types and keys."""
    known = {}
    for row in _columns(session, version_id):
        parts = row["name"].split(".")
        if len(parts) != 3:
            continue
        known[(parts[0], parts[1], parts[2])] = row
    return known


def _table_keys(session, version_id: int) -> dict[str, list[str]]:
    """Primary keys by table, from the structure scan."""
    keys = {}
    for entry in list_entries(session, version_id, kinds=["table"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        schema, name = details.get("schema") or "", details.get("name") or ""
        if schema and name:
            keys[f"{schema}.{name}"] = list(details.get("primary_key") or [])
    return keys


def _anchor_table(proposal: dict) -> str | None:
    """The proposal's own table: its first table evidence, then columns."""
    for reference in proposal.get("evidence") or []:
        if reference.startswith("table:"):
            return reference[len("table:") :]
    for reference in proposal.get("evidence") or []:
        if reference.startswith("column:"):
            return reference[len("column:") :].rsplit(".", 1)[0]
    return None


def _dimension_key(candidate: DimensionCandidate) -> str:
    """Shared dimension keys: time by grain, attributes by column."""
    if candidate.grain:
        return f"dimension.{candidate.grain}"
    return f"dimension.{candidate.column}"


def build_dimension_input(session, version_id: int, proposals: list[dict]) -> dict:
    """Everything the split proposer gets: columns, labels and proposals."""
    tables = _tables(session, version_id)
    columns = _columns(session, version_id)
    labels: dict[str, list[str]] = {}
    for row in columns:
        parts = row["name"].split(".")
        if len(parts) == 3:
            labels.setdefault(f"{parts[0]}.{parts[1]}", []).append(parts[2])
    return {
        "tables": [{"name": row["name"]} for row in tables],
        "columns": [
            {"name": row["name"], "type": row["type"], "labels": labels.get(name, [])}
            for row in columns
            for name in [row["name"].rsplit(".", 1)[0]]
        ],
        "proposals": [
            {
                "key": proposal["key"],
                "name": proposal["name"],
                "splits": proposal.get("splits") or [],
            }
            for proposal in proposals
        ],
    }


def _validate_candidate(
    candidate: DimensionCandidate, proposal_known: bool, known: dict
) -> tuple[dict | None, str]:
    """Checked split parts, or None with the warning to say."""
    if not proposal_known:
        return None, f"I left out a split for an unknown term: {candidate.term}."
    schema, _, table = candidate.table.partition(".")
    column = candidate.column.strip()
    if not schema or not table or (schema, table, column) not in known:
        return None, f"I left out the {column or 'empty'} split: it names no learned column."
    if candidate.grain:
        if candidate.grain not in GRAINS:
            return None, f"I left out the {column} split: {candidate.grain} isn't a time grain."
        column_type = known[(schema, table, column)].get("type") or ""
        if not any(token in column_type.lower() for token in DATE_TYPES):
            return None, f"I left out the {column} split: it isn't a date column."
    if candidate.label_column and (schema, table, candidate.label_column) not in known:
        return None, f"I left out the {column} split: {candidate.label_column} isn't on {table}."
    return (
        {
            "schema": schema,
            "table": table,
            "column": column,
            "label_column": candidate.label_column,
            "grain": candidate.grain,
        },
        "",
    )


def discover_dimensions(ctx: StepContext, proposals: list[dict]) -> int:
    """Propose splits, check them, persist dimensions, attach them to terms."""
    form = get_ai().run(
        FIND_DIMENSIONS_JOB,
        build_dimension_input(ctx.session, ctx.version_id, proposals),
        DimensionForm,
        app="learner",
        learning_run_id=ctx.run_id,
    )
    known = _known_columns(ctx.session, ctx.version_id)
    keys = _table_keys(ctx.session, ctx.version_id)
    links = load_build_context(ctx.session, ctx.version_id).links
    by_key = {proposal["key"]: proposal for proposal in proposals}
    seen: dict[str, str] = {}
    kept = 0
    for candidate in form.dimensions[:MAX_DIMENSIONS]:
        proposal = by_key.get(candidate.term)
        checked, warning = _validate_candidate(candidate, proposal is not None, known)
        if checked is None:
            ctx.say("warning", warning)
            continue
        schema, table, column = checked["schema"], checked["table"], checked["column"]
        dim_key = _dimension_key(candidate)
        full_table = f"{schema}.{table}"
        if dim_key in seen and seen[dim_key] != f"{full_table}.{column}":
            ctx.say(
                "warning",
                f"I left out the {column} split: {dim_key} already means {seen[dim_key]}.",
            )
            continue
        seen.setdefault(dim_key, f"{full_table}.{column}")
        if not _attach_dimension(ctx, proposal, checked, full_table, keys, links):
            continue
        kept += 1
    if len(form.dimensions) > MAX_DIMENSIONS:
        ctx.say("warning", f"I kept the first {MAX_DIMENSIONS} splits and left out the rest.")
    return kept


def _attach_dimension(
    ctx: StepContext,
    proposal: dict,
    checked: dict,
    full_table: str,
    keys: dict[str, list[str]],
    links: list,
) -> bool:
    """Check one split, persist it, attach it; False leaves it out."""
    column, label_column, grain = checked["column"], checked["label_column"], checked["grain"]
    base = _anchor_table(proposal)
    unique_with: list[dict] = []
    if base is not None and full_table != base:
        base_key = keys.get(base) or []
        if not base_key:
            ctx.say(
                "warning",
                f"I left out the {column} split: {base} has no known key.",
            )
            return False
        proof, info = infer_unique_with(
            lambda sql: run_query(ctx, "dimension_uniqueness", sql).rows,
            base,
            base_key,
            full_table,
            column,
            links,
        )
        if proof is not None:
            unique_with.append(proof.model_dump())
        elif info["reason"] not in ("no-overlap",):
            ctx.say(
                "warning",
                f"I left out the {column} split: its uniqueness is unproven.",
            )
            return False
    dim_key = f"dimension.{grain}" if grain else f"dimension.{column}"
    entry_key = dim_key
    existing = get_entry(ctx.session, ctx.version_id, entry_key)
    if existing is not None:
        before = existing.details if isinstance(existing.details, dict) else {}
        if (before.get("table"), before.get("column")) != (full_table, column):
            ctx.say(
                "warning",
                f"I left out the {column} split: {entry_key} is taken.",
            )
            return False
    details = DimensionDetails(
        kind="time" if grain else "attribute",
        table=full_table,
        column=column,
        label_column=label_column,
        grain=grain or None,
        unique_with=unique_with,
    )
    upsert_entry(
        ctx.session,
        ctx.version_id,
        entry_key,
        "dimension",
        dim_key,
        f"Split by {full_table}.{column}.",
        details.model_dump(),
        "checked",
        [dict(SOURCE_DIMENSION)],
        REASON_DIMENSION,
    )
    proposal.setdefault("dimensions", [])
    if dim_key not in proposal["dimensions"]:
        proposal["dimensions"].append(dim_key)
    return True


def _save(
    ctx: StepContext,
    proposals: list[dict],
    dimensions_done: bool,
    recipes_done: bool = False,
    recipe_failures: list[dict] | None = None,
) -> None:
    """Proposals live in the run's progress, marked untested, with a checkpoint."""
    run = ctx.session.get(LearningRun, ctx.run_id)
    time_zone = get_setting(ctx.session, "time_zone") or "UTC"
    progress = dict(run.progress or {})
    saved = progress.get(STEP_NAME) or {}
    progress[STEP_NAME] = {
        "proposals": proposals,
        "time_zone": time_zone,
        "discovered_at": saved.get("discovered_at") or datetime.now(UTC).isoformat(),
        "dimensions_done": dimensions_done,
        "recipes_done": recipes_done or saved.get("recipes_done", False),
        "recipe_failures": recipe_failures
        if recipe_failures is not None
        else saved.get("recipe_failures", []),
    }
    run.progress = progress
    flag_modified(run, "progress")
    ctx.session.flush()


def run_job(info: JobInfo, ctx: StepContext) -> None:
    """The in-run job: terms first, then splits, checkpointing between."""
    try:
        proposals = _ours(ctx).get("proposals") or []
        if not proposals:
            proposals = discover_terms(ctx)
            _save(ctx, proposals, dimensions_done=False)
        if not _ours(ctx).get("dimensions_done"):
            kept = discover_dimensions(ctx, proposals)
            _save(ctx, proposals, dimensions_done=True)
            ctx.say("found", f"Kept {kept} checked split(s) for the terms.")
        if not _ours(ctx).get("recipes_done"):
            from charie.learner.steps import recipes as recipes_step

            kept, failures = recipes_step.discover_and_test(ctx, proposals)
            _save(ctx, proposals, dimensions_done=True, recipes_done=True, recipe_failures=failures)
    except SpendingPaused:
        raise
    except Exception as err:  # noqa: BLE001 (the worker retries first; see below)
        if info.attempts >= 3:
            message = err.message if isinstance(err, AiError) else "Something went wrong."
            ctx.say("warning", f"Couldn't propose business numbers: {message}")
            return
        raise
    ctx.say(
        "found",
        "Candidate terms stay proposals until recipe checks pass.",
    )


def finish_step(ctx: StepContext) -> None:
    """Count what discovery proposed, kept and tested."""
    ours = _ours(ctx)
    proposals = ours.get("proposals") or []
    if not proposals:
        ctx.say("found", "No business numbers proposed.")
        return
    kept = sum(len(proposal.get("dimensions") or []) for proposal in proposals)
    tested = sum(
        1
        for entry in list_entries(ctx.session, ctx.version_id, kinds=["metric"])
        if entry.confidence == "checked"
    )
    ctx.say(
        "found",
        f"{len(proposals)} candidate business number(s) with {kept} checked split(s); "
        f"{tested} tested recipe(s) can be trusted.",
    )


BUSINESS_NUMBERS_STEP = Step(
    name=STEP_NAME,
    title="Propose business numbers",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="No business numbers to propose yet, so I skipped this step.",
)

register_step(BUSINESS_NUMBERS_STEP)
register_step_handler(STEP_NAME)
