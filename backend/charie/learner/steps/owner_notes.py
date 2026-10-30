"""Step 1: read the owner notes and sort them into rules (P07.5)."""

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from charie.learner.number_check import find_new_numbers
from charie.learner.runs import register_step_handler
from charie.learner.steps.base import Step, StepContext, register_step
from charie.shared.ai.client import get_ai
from charie.shared.knowledge.keys import note_key, rule_key, style_key
from charie.shared.knowledge.store import list_entries, remove_entry, upsert_entry
from charie.shared.tables.sources import OwnerNote

JOB_KIND = "sort_owner_notes"

REASON_SORTED = "Sorted from your notes"
REASON_GONE = "No longer in your notes"

RuleType = Literal[
    "never_use_table", "always_filter", "exclude_values", "currency", "required_note"
]
HintKind = Literal["how_to", "code", "event", "data_problem", "default", "calendar"]


class HardRule(BaseModel):
    """One hard rule: code enforces it."""

    title: str = Field(description="Under 10 words.")
    meaning: str = Field(description="One or two plain sentences.")
    quote: str = Field(description="The exact words from the notes.")
    rule_type: RuleType = Field(description="One of the five rule types.")
    table: str = Field(default="", description="The table, when the rule names one.")
    column: str = Field(default="", description="The column, when the rule names one.")
    values: list[str] = Field(default=[], description="The kept or left-out values.")
    currency: str = Field(default="", description="The currency code, for money rules.")
    note_text: str = Field(default="", description="The note, for required-note rules.")
    applies_to_tables: list[str] = Field(default=[], description="Tables the note applies to.")
    applies_to_words: list[str] = Field(default=[], description="Words the note applies to.")


class StyleRule(BaseModel):
    """One style rule: the writer follows it."""

    title: str = Field(description="Under 10 words.")
    meaning: str = Field(description="One or two plain sentences.")
    quote: str = Field(description="The exact words from the notes.")
    topics: list[str] = Field(default=[], description="What the rule is about.")


class DataHint(BaseModel):
    """One data hint: something Charie should remember."""

    title: str = Field(description="Under 10 words.")
    meaning: str = Field(description="One or two plain sentences.")
    quote: str = Field(description="The exact words from the notes.")
    kind: HintKind = Field(description="The kind of hint.")
    tables: list[str] = Field(default=[], description="Tables the hint mentions.")
    columns: list[str] = Field(default=[], description="Columns the hint mentions.")


class SortOwnerNotesForm(BaseModel):
    """The fixed form the sort job answers in."""

    hard_rules: list[HardRule] = Field(default=[], description="Hard rules from the notes.")
    style_rules: list[StyleRule] = Field(default=[], description="Style rules from the notes.")
    data_hints: list[DataHint] = Field(default=[], description="Data hints from the notes.")


def _fold(text: str) -> str:
    """Lowercase without whitespace: quotes match loosely."""
    return re.sub(r"\s+", "", (text or "").lower())


def _count_text(hard: int, style: int, hints: int) -> str:
    """`2 hard rules, 6 style rules and 14 hints` (singular for one)."""

    def part(count: int, one: str, many: str) -> str:
        return f"{count} {one}" if count == 1 else f"{count} {many}"

    return (
        f"{part(hard, 'hard rule', 'hard rules')}, "
        f"{part(style, 'style rule', 'style rules')} and "
        f"{part(hints, 'hint', 'hints')}"
    )


def make_jobs(ctx: StepContext) -> list[dict]:
    """One job for the newest non-empty notes; none without notes."""
    note = ctx.session.scalar(select(OwnerNote).order_by(OwnerNote.id.desc()).limit(1))
    if note is None or not note.text_.strip():
        return []
    return [{"owner_notes_id": note.id}]


def _meaning(title: str, meaning: str, quote: str) -> str:
    """The meaning, unless it types a number the quote never said."""
    if find_new_numbers([title, meaning], quote):
        return quote
    return meaning


def run_job(info, ctx: StepContext) -> None:
    """Sort the notes with the AI, then write the entries it kept."""
    session = ctx.session
    note = session.get(OwnerNote, info.payload.get("owner_notes_id"))
    if note is None or not note.text_.strip():
        return
    folded = _fold(note.text_)
    form = get_ai().run(
        JOB_KIND,
        {"notes": note.text_},
        SortOwnerNotesForm,
        app="learner",
        learning_run_id=ctx.run_id,
    )
    at = note.saved_at.isoformat() if note.saved_at else None
    used: set[str] = set()
    new_keys: set[str] = set()

    def claim(base: str) -> str:
        """This batch's key: the base, or _2, _3 when it repeats."""
        key, number = base, 2
        while key in used:
            key, number = f"{base}_{number}", number + 1
        used.add(key)
        new_keys.add(key)
        return key

    for item in form.hard_rules:
        if _fold(item.quote) not in folded:
            ctx.say("warning", f"I left out “{item.title}”: its words aren't in your notes.")
            continue
        key = claim(rule_key(item.rule_type, item.title))
        upsert_entry(
            session,
            ctx.version_id,
            key,
            "rule",
            item.title,
            _meaning(item.title, item.meaning, item.quote),
            {
                "rule_type": item.rule_type,
                "table": item.table,
                "column": item.column,
                "values": item.values,
                "currency": item.currency,
                "note_text": item.note_text,
                "applies_to_tables": item.applies_to_tables,
                "applies_to_words": item.applies_to_words,
            },
            "confirmed",
            [{"type": "owner_notes", "quote": item.quote, "at": at}],
            REASON_SORTED,
        )
        ctx.say("found", f"Hard rule: {item.title}.")
    for item in form.style_rules:
        if _fold(item.quote) not in folded:
            ctx.say("warning", f"I left out “{item.title}”: its words aren't in your notes.")
            continue
        key = claim(style_key(item.title))
        upsert_entry(
            session,
            ctx.version_id,
            key,
            "style",
            item.title,
            _meaning(item.title, item.meaning, item.quote),
            {"topics": item.topics},
            "confirmed",
            [{"type": "owner_notes", "quote": item.quote, "at": at}],
            REASON_SORTED,
        )
    for item in form.data_hints:
        if _fold(item.quote) not in folded:
            ctx.say("warning", f"I left out “{item.title}”: its words aren't in your notes.")
            continue
        key = claim(note_key(item.kind, item.title))
        upsert_entry(
            session,
            ctx.version_id,
            key,
            item.kind,
            item.title,
            _meaning(item.title, item.meaning, item.quote),
            {"tables": item.tables, "columns": item.columns},
            "confirmed",
            [{"type": "owner_notes", "quote": item.quote, "at": at}],
            REASON_SORTED,
        )
    for entry in list_entries(session, ctx.version_id):
        if entry.key in new_keys:
            continue
        if any(source.get("type") == "owner_notes" for source in entry.sources):
            remove_entry(session, ctx.version_id, entry.key, REASON_GONE)
    note.sorted_at = datetime.now(UTC)
    counts = _counts(session, ctx.version_id)
    ctx.say("found", f"Sorted your notes: {_count_text(*counts)}.")


def _counts(session, version_id: int) -> tuple[int, int, int]:
    """Hard rules, style rules and hints from the last sort."""
    hard = style = hints = 0
    for entry in list_entries(session, version_id):
        if not any(source.get("type") == "owner_notes" for source in entry.sources):
            continue
        if entry.kind == "rule":
            hard += 1
        elif entry.kind == "style":
            style += 1
        else:
            hints += 1
    return hard, style, hints


def finish_step(ctx: StepContext) -> None:
    """The bare counts, for the run summary."""
    ctx.say("found", _count_text(*_counts(ctx.session, ctx.version_id)) + ".")


OWNER_NOTES_STEP = Step(
    name="owner_notes",
    title="Read your notes",
    job_kind=JOB_KIND,
    make_jobs=make_jobs,
    run_job=run_job,
    finish=finish_step,
    empty_note="You haven't added notes yet, so I skipped this step.",
)

register_step(OWNER_NOTES_STEP)
register_step_handler("owner_notes")
