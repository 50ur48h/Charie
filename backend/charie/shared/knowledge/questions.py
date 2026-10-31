"""Owner questions 1: topics, ranking, writing and option numbers (P09.5).

Uncertainty becomes a bounded ranked set of questions. Code gathers
topics (conflicts, recipe failures, guessed defaults/calendar, unresolved
business numbers), ranks them by safety impact, affected size and stable
key, and caps new questions at twenty per run. The AI writes plain
wording and option proposals; code validates the options and calculates
each affected recipe with the proposed interpretation. A failed
calculation says so honestly; the AI never types amounts.
"""

import hashlib
import json
from dataclasses import dataclass, field, replace
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from charie.shared.ai.client import get_ai
from charie.shared.knowledge.query_builder import (
    DateRange,
    QueryRequest,
    build_query,
    load_build_context,
)
from charie.shared.knowledge.recipe import Recipe
from charie.shared.knowledge.store import get_entry, list_entries
from charie.shared.safety.catalog import Catalog, Link, RequiredFilter
from charie.shared.safety.sql_check import check_sql
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import OwnerQuestion

JOB_KIND = "write_owner_questions"

MAX_NEW_QUESTIONS = 20

FAILED_NUMBER_TEXT = "Could not calculate this option."

ORIGIN_RANK = {
    "conflict": 0,
    "recipe": 1,
    "default": 2,
    "calendar": 2,
    "business": 3,
    "todo": 3,
}


@dataclass(frozen=True)
class QuestionTopic:
    """One uncertainty, before it becomes a question."""

    origin: str
    topic: str
    entry_key: str = ""
    affects: tuple = ()
    metric_key: str = ""
    context: dict = field(default_factory=dict)


def _conflict_topics(session, version_id: int) -> list[QuestionTopic]:
    topics = []
    for entry in list_entries(session, version_id):
        if entry.confidence != "conflicting":
            continue
        topics.append(
            QuestionTopic(
                origin="conflict",
                topic=f"Which evidence about {entry.title} is right",
                entry_key=entry.key,
                affects=(entry.key,),
                context={"title": entry.title, "sources": entry.sources or []},
            )
        )
    return topics


def _recipe_topics(session, version_id: int) -> list[QuestionTopic]:
    from charie.learner.steps import recipes as recipes_step

    topics = []
    for failure in recipes_step.failed_recipes(session, version_id):
        topics.append(
            QuestionTopic(
                origin="recipe",
                topic=f"How to fix {failure['title']}",
                entry_key=failure["key"],
                affects=(failure["key"],),
                metric_key=failure["key"],
                context={"title": failure["title"], "failed": failure["failed"]},
            )
        )
    return topics


def _business_topics(session, version_id: int) -> list[QuestionTopic]:
    from charie.learner.steps import recipes as recipes_step

    run = session.scalars(
        select(LearningRun)
        .where(LearningRun.version_id == version_id)
        .order_by(LearningRun.id.desc())
    ).first()
    if run is None:
        return []
    step_progress = (run.progress or {}).get("business_numbers") or {}
    proposals = step_progress.get("proposals") or []
    reasons = {
        item.get("term"): item.get("reasons") or []
        for item in step_progress.get("recipe_failures") or []
    }
    topics = []
    for proposal in proposals:
        name = proposal.get("name") or ""
        key = proposal.get("key") or ""
        if not name:
            continue
        if recipes_step._metric_key(name) in {
            entry.key for entry in list_entries(session, version_id, kinds=["metric"])
        }:
            continue
        topics.append(
            QuestionTopic(
                origin="business",
                topic=f"What {name} should mean",
                entry_key=key,
                context={"term": key, "name": name, "reasons": reasons.get(key, [])},
            )
        )
    return topics


def _dict_topics(dicts: list[dict]) -> list[QuestionTopic]:
    return [
        QuestionTopic(
            origin=item.get("origin") or "",
            topic=item.get("topic") or "",
            entry_key=item.get("entry_key") or "",
            affects=tuple(item.get("affects") or ()),
            metric_key=item.get("metric_key") or "",
            context=item.get("context") or {},
        )
        for item in dicts
    ]


def gather_topics(session, version_id: int) -> list[QuestionTopic]:
    """Every open uncertainty: conflicts, failures, guesses and open terms."""
    from charie.shared.knowledge.calendar import calendar_topics
    from charie.shared.knowledge.defaults import default_topics

    found = [
        *_conflict_topics(session, version_id),
        *_recipe_topics(session, version_id),
        *_dict_topics(default_topics(session, version_id)),
        *_dict_topics(calendar_topics(session, version_id)),
        *_business_topics(session, version_id),
    ]
    with_sources = []
    for item in found:
        sources = item.context.get("sources") if isinstance(item.context, dict) else None
        if not sources and item.entry_key:
            entry = get_entry(session, version_id, item.entry_key)
            if entry is not None and entry.sources:
                context = dict(item.context) if isinstance(item.context, dict) else {}
                context["sources"] = entry.sources
                item = replace(item, context=context)
        with_sources.append(item)
    return sorted(with_sources, key=lambda item: (ORIGIN_RANK.get(item.origin, 9), item.topic))


def fingerprint(topic: QuestionTopic) -> str:
    """Stable id of the evidence: the same uncertainty twice matches."""
    canonical = json.dumps(
        {
            "origin": topic.origin,
            "topic": topic.topic,
            "entry_key": topic.entry_key,
            "affects": sorted(topic.affects),
            "metric_key": topic.metric_key,
            "context": topic.context,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def topic_reach(topic: QuestionTopic) -> int:
    """How many entries and recipes it affects: the stored importance."""
    return len(set(topic.affects) | ({topic.metric_key} if topic.metric_key else set()))


def rank_topics(topics: list[QuestionTopic]) -> list[QuestionTopic]:
    """Safety impact first, then affected size, then the stable topic key."""
    return sorted(
        topics,
        key=lambda item: (ORIGIN_RANK.get(item.origin, 9), -topic_reach(item), item.topic),
    )


def select_new(
    topics: list[QuestionTopic], existing: list[tuple[str, str, str]]
) -> tuple[list[QuestionTopic], list[QuestionTopic]]:
    """Split ranked topics into new questions and still-pending ones.

    `existing` is (topic, fingerprint, status) for saved questions. Waiting
    or skipped questions with the same evidence stay asked; answered ones
    with changed evidence reopen. The cap keeps new questions bounded; the
    rest stay pending for a later run, never discarded.
    """
    asked = {(topic, code) for topic, code, status in existing if status in ("waiting", "skipped")}
    new, seen = [], set()
    for topic in rank_topics(topics):
        code = fingerprint(topic)
        if (topic.topic, code) in asked or (topic.topic, code) in seen:
            continue
        seen.add((topic.topic, code))
        new.append(topic)
    return new[:MAX_NEW_QUESTIONS], new[MAX_NEW_QUESTIONS:]


class OptionDraft(BaseModel):
    """One option in the AI's words; code fills in the number."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable option id, like a or b.")
    label: str = Field(description="Plain words, no amounts.")
    explanation: str = Field(default="", description="Why this option fits, in plain words.")
    proposal: dict = Field(
        default={}, description="Machine-readable: metric, default/value or entry."
    )


class QuestionDraft(BaseModel):
    """One question in the AI's words; code checks and numbers it."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="The topic below, copied exactly.")
    title: str = Field(description="The question in plain words.")
    body: str = Field(description="What this decides, in plain words, no amounts.")
    options: list[OptionDraft] = Field(description="Two or more options.")
    default_option: str = Field(description="The safest option id.")


class WriteQuestionsForm(BaseModel):
    """The fixed form the questions job answers in."""

    model_config = ConfigDict(extra="forbid")

    questions: list[QuestionDraft] = Field(default=[], description="One per topic below.")


def _catalog(context, tables: set[str]) -> Catalog:
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


def _metric_total(session, version_id: int, metric_key: str, run, time_zone: str) -> Decimal | None:
    """One recipe's total over its learned range, or None when unusable."""
    entry = get_entry(session, version_id, metric_key)
    if entry is None or not isinstance(entry.details, dict):
        return None
    try:
        recipe = Recipe.model_validate(entry.details)
    except ValueError:
        return None
    if recipe.kind != "simple":
        return None
    schema, _, _ = (recipe.table or "").partition(".")
    period_entry = get_entry(
        session, version_id, f"data_range.{schema}.{recipe.table.split('.')[-1]}"
    )
    if period_entry is None or not isinstance(period_entry.details, dict):
        period_entry = get_entry(session, version_id, f"data_range.{recipe.table}")
    if period_entry is None or not isinstance(period_entry.details, dict):
        return None
    details = period_entry.details
    if not details.get("date_from") or not details.get("date_to"):
        return None
    context = load_build_context(session, version_id, time_zone)
    try:
        built = build_query(
            metric_key,
            {metric_key: recipe},
            QueryRequest(
                period=DateRange(
                    start=str(details["date_from"])[:10], end=str(details["date_to"])[:10]
                )
            ),
            context,
        )
    except ValueError:
        return None
    report = check_sql(built.sql, _catalog(context, {recipe.table}))
    if not report.ok:
        return None
    try:
        rows = run(built.sql)
    except Exception:
        return None
    if not rows or not rows[0]:
        return None
    value = rows[0][0]
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _option_number(session, version_id: int, proposal: dict, run, time_zone: str) -> str:
    """The number one option gives, or the honest fallback."""
    metric_key = proposal.get("metric") or ""
    if not metric_key and proposal.get("default"):
        value = proposal.get("value") or ""
        if isinstance(value, str) and value.startswith("metric."):
            metric_key = value
    if not metric_key:
        return FAILED_NUMBER_TEXT
    total = _metric_total(session, version_id, metric_key, run, time_zone)
    if total is None:
        return FAILED_NUMBER_TEXT
    return str(total.normalize())


def _valid_options(draft: QuestionDraft) -> list[OptionDraft] | None:
    """Options with stable unique ids and a default among them, or None."""
    ids = [option.id.strip() for option in draft.options]
    if len(ids) < 2 or any(not code for code in ids) or len(set(ids)) != len(ids):
        return None
    if draft.default_option not in ids:
        return None
    kept = []
    for option in draft.options:
        if not option.label.strip():
            return None
        proposal = option.proposal if isinstance(option.proposal, dict) else {}
        keys = set(proposal) & {"metric", "default", "entry"}
        if not keys:
            return None
        kept.append(option)
    return kept


def make_owner_questions(
    session,
    version_id: int,
    topics: list[QuestionTopic],
    run,
    time_zone: str,
    source: str = "learning",
) -> tuple[list[int], list[QuestionTopic]]:
    """Rank, write, number and save questions; returns ids and pending topics."""
    existing_rows = session.scalars(select(OwnerQuestion)).all()
    existing = [
        (row.topic, (row.evidence or {}).get("fingerprint", ""), row.status)
        for row in existing_rows
    ]
    answered_labels = {}
    for row in existing_rows:
        if row.status == "answered" and isinstance(row.answer, dict):
            picked = row.answer.get("option_id")
            labels = {option.get("id"): option.get("label", "") for option in row.options or []}
            answered_labels[row.topic] = labels.get(picked, "")
    new, pending = select_new(topics, existing)
    if not new:
        return [], pending
    tested = sorted(entry.key for entry in list_entries(session, version_id, kinds=["metric"]))
    form = get_ai().run(
        JOB_KIND,
        {
            "topics": [
                {
                    "topic": item.topic,
                    "origin": item.origin,
                    "entry_key": item.entry_key,
                    "affects": sorted(item.affects),
                    "metric_key": item.metric_key,
                    "context": item.context,
                }
                for item in new
            ],
            "metrics": tested,
        },
        WriteQuestionsForm,
        app="learner",
        learning_run_id=None,
    )
    drafts = {draft.topic: draft for draft in form.questions}
    created, made = [], []
    for item in new:
        draft = drafts.get(item.topic)
        if draft is None:
            continue
        options = _valid_options(draft)
        if options is None:
            continue
        saved_options = []
        for option in options:
            saved_options.append(
                {
                    "id": option.id,
                    "label": option.label,
                    "explanation": option.explanation,
                    "number": _option_number(session, version_id, option.proposal, run, time_zone),
                    "proposal": option.proposal,
                }
            )
        body = draft.title.strip() + "\n\n" + draft.body.strip() if draft.title else draft.body
        if item.topic in answered_labels:
            earlier = answered_labels[item.topic]
            body += f"\n\nEarlier you answered “{earlier}”; the evidence changed."
            body += " Please answer again."
        row = OwnerQuestion(
            status="waiting",
            rank=0,
            importance=topic_reach(item),
            topic=item.topic,
            title=draft.title,
            body=body,
            evidence={
                "origin": item.origin,
                "entry_key": item.entry_key,
                "metric_key": item.metric_key,
                "context": item.context,
                "fingerprint": fingerprint(item),
                "sources": (item.context.get("sources") if isinstance(item.context, dict) else [])
                or [],
            },
            options=saved_options,
            default_option=draft.default_option,
            affects=sorted(set(item.affects) | ({item.metric_key} if item.metric_key else set())),
            source=source,
        )
        session.add(row)
        session.flush()
        created.append(row.id)
        made.append(item)
    for position, row_id in enumerate(created, start=1):
        session.get(OwnerQuestion, row_id).rank = position
    session.flush()
    return created, [*pending, *(item for item in new if item not in made)]
