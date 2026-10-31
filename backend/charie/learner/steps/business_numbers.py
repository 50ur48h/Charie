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

from charie.learner.steps.base import Step, StepContext, register_step, register_step_handler
from charie.learner.steps.explain_tables import UnitKind
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import AiError, SpendingPaused
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge.keys import slug
from charie.shared.knowledge.store import list_entries
from charie.shared.settings import get_setting
from charie.shared.tables.learning import Job, LearningRun
from charie.shared.tables.sources import DocFact

JOB_KIND = "find_business_terms"

STEP_NAME = "business_numbers"

REASON_PROPOSED = "Proposed from learned evidence; unchecked until recipe tests pass"

MAX_TERMS = 25
MAX_SPLITS = 5
MAX_EVIDENCE = 8
MAX_DOC_FACTS = 200


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


def make_jobs(ctx: StepContext) -> list[dict]:
    """One discovery job, unless one runs already or proposals exist."""
    progress = ctx.session.get(LearningRun, ctx.run_id).progress or {}
    if (progress.get(STEP_NAME) or {}).get("proposals"):
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


def _save(ctx: StepContext, proposals: list[dict]) -> None:
    """Proposals live in the run's progress, marked untested."""
    run = ctx.session.get(LearningRun, ctx.run_id)
    time_zone = get_setting(ctx.session, "time_zone") or "UTC"
    progress = dict(run.progress or {})
    progress[STEP_NAME] = {
        "proposals": proposals,
        "time_zone": time_zone,
        "discovered_at": datetime.now(UTC).isoformat(),
    }
    run.progress = progress
    flag_modified(run, "progress")
    ctx.session.flush()


def run_job(info: JobInfo, ctx: StepContext) -> None:
    """The in-run job: discover terms once, then save the proposals."""
    try:
        proposals = discover_terms(ctx)
    except SpendingPaused:
        raise
    except Exception as err:  # noqa: BLE001 (the worker retries first; see below)
        if info.attempts >= 3:
            message = err.message if isinstance(err, AiError) else "Something went wrong."
            ctx.say("warning", f"Couldn't propose business numbers: {message}")
            return
        raise
    _save(ctx, proposals)
    ctx.say(
        "found",
        f"{len(proposals)} candidate business number(s); "
        "they stay proposals until recipe checks pass.",
    )


def finish_step(ctx: StepContext) -> None:
    """Count what discovery proposed; nothing here is usable yet."""
    progress = ctx.session.get(LearningRun, ctx.run_id).progress or {}
    proposals = (progress.get(STEP_NAME) or {}).get("proposals") or []
    if not proposals:
        ctx.say("found", "No business numbers proposed.")
        return
    ctx.say(
        "found",
        f"{len(proposals)} candidate business number(s); "
        "they stay proposals until recipe checks pass.",
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
