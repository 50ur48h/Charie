"""The first real AI step: what is asked, and the first thinking line (P10.4).

The AI says what is asked, the period expressions and the kind of
question, plus an "I read this as…" sentence. Code checks the reply,
works out the dates and writes the first real line.
"""

import re
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import select

from charie.chat.analyst.dates import (
    DateContext,
    PeriodError,
    PeriodExpression,
    PeriodSet,
    resolve_periods,
)
from charie.chat.analyst.kb_view import KbView, load_date_context
from charie.chat.analyst.labels import fill_labels, labels_in, mixed_tokens, stray_digits
from charie.chat.analyst.references import (
    REF_RE,
    ListRef,
    PeriodShift,
    Resolved,
    Unresolved,
    ref_numbers,
    resolve_references,
)
from charie.chat.memory import memories_for_prompt
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import AiError, AiFormError
from charie.shared.db import session_scope
from charie.shared.settings import get_setting
from charie.shared.tables.chat import Message

QuestionKind = Literal[
    "clear",
    "vague_with_default",
    "vague_no_default",
    "two_meanings",
    "follow_up",
    "why",
    "documents",
    "not_in_data",
    "new_kind",
    "about_answer",
]


class Filter(BaseModel):
    """One filter: a dimension and the wanted names, as the owner spells them."""

    dimension_key: str = Field(
        default="", description="A dimension key from the knowledge summary."
    )
    values: list[str] = Field(default=[], description="Wanted names, spelled as in the name entry.")


class Ask(BaseModel):
    """One number asked for: a known metric or a new number in plain words."""

    metric_key: str = Field(default="", description="A metric key, or empty for a new number.")
    new_metric: str = Field(
        default="", description="Plain words for a number no recipe covers, or empty."
    )
    split_by: list[str] = Field(default=[], description="Up to 2 dimension keys to split by.")
    top_n: int | None = Field(default=None, description="Keep only the top rows, or empty for all.")


class ChoiceOption(BaseModel):
    """One clickable answer to a quick question."""

    id: str = Field(default="", description="Lowercase words joined by _, like by_net_sales.")
    label: str = Field(default="", description="The option in the owner's words.")


class QuickChoice(BaseModel):
    """The one quick question, asked instead of guessing."""

    text: str = Field(default="", description="The question in the owner's words.")
    options: list[ChoiceOption] = Field(default=[], description="2 to 4 options.")


class Meaning(BaseModel):
    """One meaning of a two-meaning word: a label and its metric."""

    label: str = Field(default="", description="The meaning in the owner's words.")
    metric_key: str = Field(default="", description="A metric key of this version.")


class Understanding(BaseModel):
    """The AI's reading of one question, checked by code below."""

    kind: QuestionKind = Field(description="The kind of question from the fixed list.")
    reading: str = Field(
        default="", description="I read this as… with periods as [p1], [p2]. No digits."
    )
    periods: list[PeriodExpression] = Field(
        default=[], description="The main period first, then comparisons."
    )
    asks: list[Ask] = Field(default=[], description="One item per number asked for.")
    filters: list[Filter] = Field(default=[], description="A filter for every ask.")
    defaults_used: list[str] = Field(
        default=[], description="Keys of default entries used, like default.sales."
    )
    document_topics: list[str] = Field(
        default=[], description="Short search phrases for document questions."
    )
    choice: QuickChoice | None = Field(
        default=None, description="The quick question, only for vague_no_default."
    )
    meanings: list[Meaning] = Field(
        default=[], description="Exactly 2 meanings, only for two_meanings."
    )
    about: list[str] = Field(
        default=[], description="Said refs like 812:n1, empty for the whole last answer."
    )
    missing: str = Field(
        default="", description="The thing not in the data, in a few words, no digits."
    )
    inherit: list[Literal["asks", "filters", "periods"]] = Field(
        default=[], description="Parts the question takes from the chat's focus."
    )
    list_refs: list[ListRef] = Field(default=[], description="Pointers at shown lists, at most 3.")
    period_shift: PeriodShift | None = Field(
        default=None, description="Move the chat's last periods, or null."
    )


def knowledge_summary(kb: KbView) -> str:
    """The version's metrics, dimensions, defaults and names, briefly."""
    lines = ["Metrics:"]
    titles = kb.titles()
    meanings = kb.meanings()
    for key in sorted(kb.metrics()):
        lines.append(f"- {key}: {titles.get(key, key)} — {meanings.get(key, '')}")
    lines.append("Dimensions:")
    for key in sorted(kb.dimensions()):
        lines.append(f"- {key}: {titles.get(key, key)}")
    lines.append("Defaults:")
    for word in sorted(kb.defaults()):
        entry = kb.defaults()[word]
        lines.append(f"- default.{word}: the word {word!r} means {entry.value!r}")
    lines.append("Names:")
    for key in sorted(kb.names()):
        details = kb.names()[key]
        table = details.get("table", "") if isinstance(details, dict) else ""
        items = details.get("items", []) if isinstance(details, dict) else []
        names = ", ".join(item.get("name", "") for item in items if isinstance(item, dict))
        lines.append(f"- {key} (table {table}): {names}")
    return "\n".join(lines)


def understand_input(ctx, kb: KbView) -> dict:
    """The prompt inputs: the question, the dates, earlier questions, memories."""
    with session_scope() as session:
        zone_name = get_setting(session, "time_zone") or "UTC"
        rows = session.scalars(
            select(Message)
            .where(Message.chat_id == ctx.chat_id, Message.role == "user")
            .order_by(Message.id.desc())
            .limit(6)
        ).all()
        earlier = [row.text_ for row in rows if row.text_ != ctx.question][:5]
        earlier.reverse()
        from charie.chat.analyst.chat_context import context_for_prompt, load_context

        chat_context = context_for_prompt(load_context(session, ctx.chat_id))
        memory_on = get_setting(session, "memory_on")
        memories = memories_for_prompt(session) if memory_on else []
    today = datetime.now(ZoneInfo(zone_name)).date()
    through = kb.data_through
    anchor = min(today, through) if through is not None else today
    return {
        "question": ctx.question,
        "anchor": anchor.isoformat(),
        "data_through": through.isoformat() if through is not None else "no data yet",
        "earlier": earlier,
        "chat_context": chat_context,
        "memories": memories,
        "repair": "",
    }


def _check_context(kb: KbView) -> DateContext:
    """A resolver context for validating periods (UTC today is fine here)."""
    calendar = kb.calendar()
    return DateContext(
        today=datetime.now(UTC).date(),
        data_through=kb.data_through,
        data_from=kb.data_from(),
        week_start=calendar.week_start,
        fiscal_start_month=calendar.fiscal_year_start,
        time_zone="UTC",
    )


def _name_match(kb: KbView, dimension_key: str, value: str) -> str | None:
    """The stored spelling of a filter value, or None when unknown.

    Names live on lookup tables, not the fact tables dimensions point
    at, so every name entry counts. Turning a name into an id for one
    dimension's table is the data helper's job (P10.6).
    """
    if dimension_key not in kb.dimensions():
        return None
    for entry in kb.names().values():
        if not isinstance(entry, dict):
            continue
        for item in entry.get("items", []):
            name = item.get("name", "") if isinstance(item, dict) else ""
            if name.lower() == value.lower():
                return name
    return None


def _check_choice(u: Understanding, problems: list[str], allowed: list[str]) -> None:
    """The quick question's shape: 2-4 distinct options, no digits."""
    choice = u.choice
    if choice is None:
        return
    if u.kind != "vague_no_default":
        problems.append("The quick question is only for vague_no_default.")
        return
    if not 2 <= len(choice.options) <= 4:
        problems.append("The quick question needs 2 to 4 options.")
    ids = [option.id for option in choice.options]
    if len(set(ids)) != len(ids):
        problems.append("The quick question's option ids must all be different.")
    words = " ".join([choice.text] + [option.label for option in choice.options])
    stray = stray_digits(words, allowed)
    if stray:
        problems.append(f"The quick question must not type numbers: {', '.join(stray)}.")


ABOUT_RE = re.compile(r"^\d+:[ntpq]\d+$")


def _check_about(u: Understanding, problems: list[str]) -> None:
    """About refs name one earlier message and label, like 812:n1."""
    if u.kind != "about_answer":
        if u.about:
            problems.append("About refs are only for about_answer.")
        return
    for ref in u.about:
        if not ABOUT_RE.match(ref or ""):
            problems.append("About refs look like 812:n1: the earlier message and label.")
            break


def _check_missing(u: Understanding, problems: list[str], allowed: list[str]) -> None:
    """The missing thing is a few words with no digits."""
    if u.kind != "not_in_data":
        if u.missing:
            problems.append("The missing thing is only for not_in_data.")
        return
    if not u.missing.strip():
        problems.append("not_in_data needs the missing thing in a few words.")
        return
    stray = stray_digits(u.missing or "", allowed)
    if stray:
        problems.append(f"The missing thing must not type numbers: {', '.join(stray)}.")


def _check_meanings(u: Understanding, kb: KbView, problems: list[str]) -> None:
    """Two meanings are exactly 2 known metrics of this version."""
    if u.kind != "two_meanings":
        if u.meanings:
            problems.append("Meanings are only for two_meanings.")
        return
    if len(u.meanings) != 2:
        problems.append("two_meanings needs exactly 2 meanings.")
        return
    for meaning in u.meanings:
        if meaning.metric_key not in kb.metrics():
            problems.append(
                f"Unknown meaning metric {meaning.metric_key!r}. Use a metric key from the summary."
            )


def check_understanding(u: Understanding, kb: KbView, choice_answered: bool = False) -> list[str]:
    """Every problem with the AI's reply, in words it can act on.

    Matching filter spellings are fixed in place; the reply keeps no
    problem the fallback can't describe.
    """
    problems: list[str] = []
    metrics = kb.metrics()
    dimensions = kb.dimensions()
    for pos, ask in enumerate(u.asks, start=1):
        if bool(ask.metric_key) == bool(ask.new_metric):
            problems.append(f"Ask {pos} needs exactly one of a metric key or new words.")
            continue
        if ask.metric_key and ask.metric_key not in metrics:
            problems.append(
                f"Unknown metric {ask.metric_key!r}. Use one of: {', '.join(sorted(metrics))}."
            )
        for split in ask.split_by:
            if split not in dimensions:
                problems.append(
                    f"Unknown split {split!r}. Use one of: {', '.join(sorted(dimensions))}."
                )
    for filt in u.filters:
        if filt.dimension_key not in dimensions:
            problems.append(f"Unknown filter dimension {filt.dimension_key!r}.")
            continue
        for pos, value in enumerate(filt.values):
            spelled = _name_match(kb, filt.dimension_key, value)
            if spelled is None:
                title = kb.titles().get(filt.dimension_key, filt.dimension_key)
                problems.append(f"Unknown {title} {value!r}. Use a name from the summary.")
            elif spelled != value:
                filt.values[pos] = spelled
    known_words = set(kb.defaults())
    for used in u.defaults_used:
        word = used.removeprefix("default.")
        if word not in known_words:
            problems.append(f"Unknown default {used!r}. Use one of the defaults in the summary.")
            continue
        if u.kind == "vague_with_default" and not kb.defaults()[word].value:
            problems.append(
                f'Default "{used}" has no settled meaning yet; ask a quick question instead.'
            )
    if choice_answered and u.choice is not None:
        problems.append("The user already answered your quick question. Don't ask again.")
    if len(u.list_refs) > 3:
        problems.append("list_refs holds at most 3 pointers at shown lists.")
    if u.period_shift is not None and u.period_shift.n == 0:
        problems.append("The period shift must move by at least 1 unit.")
    for num in ref_numbers(u.reading):
        if num > len(u.list_refs):
            problems.append(f"The reading names {{ref{num}}} but list_refs has no entry {num}.")
            break
    reading = REF_RE.sub(" ", u.reading)
    allowed_labels = {f"p{num}" for num in range(1, len(u.periods) + 1)}
    for label in labels_in(u.reading):
        if label not in allowed_labels:
            problems.append("The reading may only use [p1] to [pK] for its K periods.")
            break
    allowed_words = mixed_tokens(
        list(kb.titles().values()) + kb.name_spellings() + list(known_words)
    )
    _check_choice(u, problems, allowed_words)
    _check_meanings(u, kb, problems)
    _check_about(u, problems)
    _check_missing(u, problems, allowed_words)
    stray = stray_digits(reading, allowed_words)
    if stray:
        problems.append(f"The reading must not type numbers: {', '.join(stray)}.")
    try:
        resolve_periods(u.periods, _check_context(kb))
    except PeriodError as err:
        problems.append(f"The periods don't resolve: {err}.")
    return problems


def _blank_understanding() -> Understanding:
    """A reply-shaped object the fallbacks can fix without the AI."""
    return Understanding(
        kind="vague_no_default",
        reading="",
        periods=[],
        asks=[],
        filters=[],
        defaults_used=[],
        document_topics=[],
        about=[],
        missing="",
        inherit=[],
        list_refs=[],
        period_shift=None,
        choice=None,
        meanings=[],
    )


def _choice_answered(ctx) -> bool:
    """Whether this question answers the chat's waiting quick question."""
    from charie.chat.analyst.chat_context import load_context

    with session_scope() as session:
        pending = load_context(session, ctx.chat_id).pending_choice
    return pending is not None


def _add_meaning_asks(u: Understanding) -> None:
    """Code adds an ask for each meaning, so both numbers get fetched."""
    if u.kind != "two_meanings":
        return
    have = {ask.metric_key for ask in u.asks}
    for meaning in u.meanings:
        if meaning.metric_key and meaning.metric_key not in have:
            u.asks.append(Ask(metric_key=meaning.metric_key))
            have.add(meaning.metric_key)


def _metric_titles(u: Understanding, kb: KbView) -> list[str]:
    """Titles of the asked metrics that survived the checks."""
    titles = kb.titles()
    return [titles[ask.metric_key] for ask in u.asks if ask.metric_key and ask.metric_key in titles]


def _fallback_periods() -> list[PeriodExpression]:
    """The latest full month, when the AI's periods can't be used."""
    return [PeriodExpression(kind="last_full_unit", unit="month")]


def apply_fallbacks(
    u: Understanding, kb: KbView, date_ctx: DateContext, problems: list[str]
) -> list[str]:
    """Fix what the retry couldn't; every fix is saved for the writer.

    Returns the note lines, in the owner's words.
    """
    notes: list[str] = []
    kept_asks: list[Ask] = []
    metrics = kb.metrics()
    dimensions = kb.dimensions()
    for ask in u.asks:
        if bool(ask.metric_key) == bool(ask.new_metric):
            continue
        if ask.metric_key and ask.metric_key not in metrics:
            continue
        ask.split_by = [split for split in ask.split_by if split in dimensions]
        kept_asks.append(ask)
    u.asks = kept_asks
    kept_filters: list[Filter] = []
    for filt in u.filters:
        if filt.dimension_key not in dimensions:
            continue
        title = kb.titles().get(filt.dimension_key, filt.dimension_key)
        kept_values: list[str] = []
        for value in filt.values:
            spelled = _name_match(kb, filt.dimension_key, value)
            if spelled is None:
                notes.append(f'I couldn\'t match "{value}" to a {title} I know, so I left it out.')
            else:
                kept_values.append(spelled)
        if kept_values:
            filt.values = kept_values
            kept_filters.append(filt)
    u.filters = kept_filters
    u.defaults_used = [
        used for used in u.defaults_used if used.removeprefix("default.") in kb.defaults()
    ]
    bare = REF_RE.sub(" ", u.reading)
    allowed_labels = {f"p{num}" for num in range(1, len(u.periods) + 1)}
    reading_ok = all(label in allowed_labels for label in labels_in(u.reading))
    allowed_words = mixed_tokens(
        list(kb.titles().values()) + kb.name_spellings() + list(kb.defaults())
    )
    if not reading_ok or stray_digits(bare, allowed_words):
        names = _metric_titles(u, kb) or ["what you asked"]
        u.reading = f"I read this as {', '.join(names)} for [p1]."
        if len(u.periods) > 1:
            u.reading += " Compared with [p2]."
    try:
        resolve_periods(u.periods, date_ctx)
    except PeriodError:
        u.periods = _fallback_periods()
        notes.append("I couldn't use the period I picked, so I used the latest full month.")
    _ = problems
    return notes


def _default_meaning(word: str, kb: KbView) -> str:
    """The meaning behind a used default, in the owner's words."""
    value = kb.defaults()[word].value
    if value in kb.titles():
        return kb.titles()[value]
    return value.replace("_", " ")


def _line_body(u: Understanding, kb: KbView, periods: PeriodSet, notes: list[str]) -> str:
    """The done line: the filled reading, defaults, dates and notes."""
    values = {period.label: period.text for period in periods.periods}
    parts = [fill_labels(u.reading, values)]
    for used in u.defaults_used:
        word = used.removeprefix("default.")
        parts.append(f'I used the default meaning of "{word}": {_default_meaning(word, kb)}.')
    if periods.anchor_note:
        parts.append(periods.anchor_note)
    for period in periods.periods:
        if period.note:
            parts.append(period.note)
    parts.extend(notes)
    return "\n".join(part for part in parts if part)


def _line_details(u: Understanding, periods: PeriodSet) -> dict:
    """The expandable details: the kind and every resolved period."""
    return {
        "kind": u.kind,
        "periods": [
            {
                "label": period.label,
                "short_text": period.expression.short_text(),
                "start": period.start.isoformat(),
                "end": period.end.isoformat(),
                "partial": period.partial,
            }
            for period in periods.periods
        ],
    }


def _resolve_follow_up(ctx, u):
    """Work out chat pointers by code; None when the question has none."""
    if not u.inherit and not u.list_refs and u.period_shift is None:
        return None
    from charie.chat.analyst.chat_context import load_context

    with session_scope() as session:
        context = load_context(session, ctx.chat_id)
    return resolve_references(u, context)


def understand(ctx) -> None:
    """Run the first AI step and write its line; fallbacks cover failures."""
    with session_scope() as session:
        kb = KbView.load(session, ctx.kb_version_id)
        date_ctx = load_date_context(session, None, kb)
    inputs = understand_input(ctx, kb)
    answered_choice = _choice_answered(ctx)
    summary = knowledge_summary(kb)
    ai = get_ai()
    seq = ctx.log.start("step", "Reading your question")
    try:
        first = ai.run(
            "understand_question",
            inputs,
            Understanding,
            app="chat",
            message_id=ctx.message_id,
            knowledge_summary=summary,
            knowledge_version=ctx.kb_version_id,
            already_running=False,
        )
        problems = check_understanding(first, kb, answered_choice)
        if problems:
            second_inputs = dict(inputs, repair="; ".join(problems))
            second = ai.run(
                "understand_question",
                second_inputs,
                Understanding,
                app="chat",
                message_id=ctx.message_id,
                knowledge_summary=summary,
                knowledge_version=ctx.kb_version_id,
                already_running=False,
            )
            problems = check_understanding(second, kb, answered_choice)
            u = second
        else:
            u = first
    except (AiFormError, PeriodError, AiError) as err:
        u = _blank_understanding()
        problems = [str(err)]
    _add_meaning_asks(u)
    notes = apply_fallbacks(u, kb, date_ctx, problems)
    if answered_choice and u.choice is not None:
        ctx.choice_failed = True
        ctx.understanding = u
        ctx.periods = PeriodSet()
        ctx.problems = list(problems)
        return
    resolution = _resolve_follow_up(ctx, u)
    if isinstance(resolution, Unresolved):
        ctx.unresolved_follow_up = resolution.words
        ctx.log.add(
            "decision",
            "Couldn't match the follow-up",
            f'I couldn\'t match "{resolution.words}" to anything shown earlier in this chat.',
        )
        ctx.understanding = u
        ctx.periods = PeriodSet()
        ctx.problems = list(problems)
        return
    if isinstance(resolution, Resolved):
        u = resolution.understanding
        if resolution.lines:
            ctx.log.add("decision", "Understood the follow-up", "\n".join(resolution.lines))
    periods = resolve_periods(u.periods, date_ctx)
    ctx.understanding = u
    ctx.periods = periods
    ctx.problems = list(problems)
    for note in notes:
        ctx.log.add("note", note)
    ctx.log.finish(
        seq,
        status="done",
        title="Understood the question",
        body=_line_body(u, kb, periods, notes),
        details=_line_details(u, periods),
    )
