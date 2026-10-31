"""Step 9, defaults: default meanings for vague business words (P09.4).

The AI proposes defaults from tested metrics and owner notes; code owns
the keys and checks every value (metric references, supported periods).
Owner-confirmed defaults are never silently changed: a confirmed entry
keeps its value, and reruns keep stable keys. Guessed defaults stay
visible for owner questions (P09.5); calendar stays a separate entry.
"""

import re

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from charie.learner.steps.base import Step, StepContext, register_step, register_step_handler
from charie.shared.ai.client import get_ai
from charie.shared.knowledge.defaults import (
    DEFAULT_KEYS,
    default_topics,
    tested_metric_keys,
    validate_default,
)
from charie.shared.knowledge.store import get_entry, list_entries, upsert_entry
from charie.shared.tables.sources import OwnerNote

JOB_KIND = "propose_defaults"
STEP_NAME = "defaults"

REASON_DEFAULTS = "Guessed from tested metrics and your notes; confirm it in questions"

WORD_FOR_KEY = {
    "default.sales": "sales",
    "default.last_week": "last_week",
    "default.period": "period",
    "default.best": "best",
}


class DefaultProposal(BaseModel):
    """One default in the AI's words; code owns keys and checks."""

    model_config = ConfigDict(extra="forbid")

    word: str = Field(description="One of sales, last_week, period or best.")
    value: str = Field(default="", description="The meaning; empty while ambiguous.")
    metrics: list[str] = Field(default=[], description="Affected tested metric keys.")
    quote: str = Field(default="", description="The exact owner words behind it, or empty.")


class ProposeDefaultsForm(BaseModel):
    """The fixed form the defaults job answers in."""

    model_config = ConfigDict(extra="forbid")

    defaults: list[DefaultProposal] = Field(
        default=[], description="One default per word, most critical first."
    )


def _key_for(word: str) -> str:
    for key, known in WORD_FOR_KEY.items():
        if known == word:
            return key
    return ""


def _notes_text(session) -> str:
    note = session.scalar(select(OwnerNote).order_by(OwnerNote.id.desc()).limit(1))
    if note is None or not note.text_.strip():
        return ""
    return note.text_


def _fold(text: str) -> str:
    """Lowercase without whitespace: quotes match loosely."""
    return re.sub(r"\s+", "", (text or "").lower())


def build_defaults_input(session, version_id: int) -> dict:
    """Words, tested metrics and notes for the proposal job."""
    tested = sorted(tested_metric_keys(session, version_id))
    metrics = []
    for key in tested:
        entry = get_entry(session, version_id, key)
        metrics.append({"key": key, "title": entry.title if entry else key})
    return {
        "words": sorted(WORD_FOR_KEY.values()),
        "metrics": metrics,
        "notes": _notes_text(session),
    }


def discover_defaults(ctx: StepContext) -> tuple[int, list[dict]]:
    """Propose, check and save defaults; returns kept count and failures."""
    session = ctx.session
    tested = tested_metric_keys(session, ctx.version_id)
    folded = _fold(_notes_text(session))
    form = get_ai().run(
        JOB_KIND,
        {**build_defaults_input(session, ctx.version_id), "repair": ""},
        ProposeDefaultsForm,
        app="learner",
        learning_run_id=ctx.run_id,
    )
    kept, failures = 0, []
    seen: set[str] = set()
    for proposal in form.defaults:
        key = _key_for(proposal.word)
        if not key or key in seen:
            continue
        seen.add(key)
        old = get_entry(session, ctx.version_id, key)
        if old is not None and old.confidence == "confirmed":
            continue
        problems = validate_default(proposal.word, proposal.value, tested)
        unknown_metrics = [metric for metric in proposal.metrics if metric not in tested]
        if unknown_metrics:
            problems.append(f"Unknown tested metrics: {', '.join(sorted(unknown_metrics))}.")
        if proposal.quote and _fold(proposal.quote) not in folded:
            problems.append("The quote is not in your notes.")
        if problems:
            failures.append({"key": key, "reasons": problems})
            continue
        details = {
            "word": proposal.word,
            "value": proposal.value,
            "evidence": (
                [{"type": "owner_notes", "quote": proposal.quote}] if proposal.quote else []
            ),
            "metrics": [metric for metric in proposal.metrics if metric in tested],
        }
        if proposal.word == "sales" and proposal.value:
            details["metrics"] = sorted(set(details["metrics"]) | {proposal.value})
        upsert_entry(
            session,
            ctx.version_id,
            key,
            "default",
            proposal.word.replace("_", " "),
            proposal.value or "Unresolved: needs your answer.",
            details,
            "guessed",
            [{"type": "ai", "text": REASON_DEFAULTS}],
            REASON_DEFAULTS,
        )
        kept += 1
    guessed = len(default_topics(session, ctx.version_id))
    ctx.say("found", f"Kept {kept} default meaning(s); {guessed} await your answer.")
    return kept, failures


def make_jobs(ctx: StepContext) -> list[dict]:
    """One proposal job until every default word has an entry."""
    have = {
        entry.key
        for entry in list_entries(ctx.session, ctx.version_id, kinds=["default"])
        if entry.key in DEFAULT_KEYS
    }
    if set(DEFAULT_KEYS) <= have:
        return []
    return [{"step": STEP_NAME}]


def run_job(info, ctx: StepContext) -> None:
    """Propose and save the defaults for this run."""
    discover_defaults(ctx)


def finish_step(ctx: StepContext) -> None:
    """How many defaults await an answer, for the run summary."""
    ctx.say(
        "found", f"{len(default_topics(ctx.session, ctx.version_id))} default(s) await your answer."
    )


DEFAULTS_STEP = Step(
    name="defaults",
    title="Default meanings",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="No vague words need defaults yet.",
)

register_step(DEFAULTS_STEP)
register_step_handler("defaults")
