"""Owner answers: apply them to the draft, retest, stay honest (P09.6).

An answer picks one validated option or writes free text. Selected
proposals update the draft (defaults confirmed, calendar confirmed with
its setting, conflicts resolved, metrics and entries retested); free
text becomes a learner to-do until P09.7 converts it. Resubmitting the
same answer is idempotent; changing an answered question sends the
saved answer back as `previous`, and anything else that differs
conflicts instead of silently replacing it. Published knowledge never
changes here.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from charie.shared.knowledge.store import get_entry, upsert_entry
from charie.shared.knowledge.todos import add_learner_todo
from charie.shared.knowledge.versions import get_or_create_draft
from charie.shared.tables.questions import OwnerQuestion


class AnswerNotFound(LookupError):
    """No question with that id."""


class BadAnswer(ValueError):
    """The answer does not fit this question."""


class AnswerConflict(ValueError):
    """The question already has a different answer."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _core(stored: dict | None) -> dict | None:
    """The stored choice without provenance, for idempotency checks."""
    if not isinstance(stored, dict):
        return None
    if isinstance(stored.get("option_id"), str):
        return {"option_id": stored["option_id"]}
    if isinstance(stored.get("text"), str):
        return {"text": stored["text"]}
    return None


def _apply_default(
    session, version_id: int, proposal: dict, label: str
) -> tuple[list[dict], list[str]]:
    """Confirm one default meaning; returns applied changes and retest keys."""
    from charie.shared.knowledge.defaults import tested_metric_keys, validate_default

    key = proposal.get("default") or ""
    value = proposal.get("value") or ""
    entry = get_entry(session, version_id, key)
    if entry is None or entry.kind != "default":
        raise BadAnswer("That answer does not fit this question.")
    details = entry.details if isinstance(entry.details, dict) else {}
    problems = validate_default(
        details.get("word") or "", value, tested_metric_keys(session, version_id)
    )
    if problems:
        raise BadAnswer(problems[0])
    before = details.get("value") or ""
    changed = dict(details)
    changed["value"] = value
    if value.startswith("metric."):
        changed["metrics"] = sorted(set(changed.get("metrics") or []) | {value})
    upsert_entry(
        session,
        version_id,
        key,
        "default",
        entry.title,
        value or entry.meaning,
        changed,
        "confirmed",
        [
            *(entry.sources if isinstance(entry.sources, list) else []),
            {"type": "owner_answer", "text": label},
        ],
        "Confirmed by the owner.",
    )
    tables = _retest_tables(session, version_id, [value]) if value.startswith("metric.") else []
    return [{"entry": key, "before": before, "after": value}], tables


def _apply_calendar(session, version_id: int, proposal: dict, run) -> tuple[list[dict], dict]:
    """Confirm the calendar: setting, draft and time-recipe retests."""
    from charie.shared.knowledge.calendar import confirm_calendar

    values = proposal.get("calendar")
    if not isinstance(values, dict) or set(values) - {
        "time_zone",
        "week_start",
        "fiscal_year_start",
    }:
        raise BadAnswer("That answer does not fit this question.")
    try:
        outcome = confirm_calendar(session, version_id, values, run)
    except ValueError as err:
        raise BadAnswer(str(err)) from err
    return [{"entry": "calendar.business"}], outcome


def _retest_tables(session, version_id: int, keys: list[str]) -> list[str]:
    """Tables behind the affected metrics: what retest_affected matches on."""
    tables = []
    for key in keys:
        entry = get_entry(session, version_id, key)
        details = entry.details if entry is not None and isinstance(entry.details, dict) else {}
        if details.get("table"):
            tables.append(details["table"])
    return tables or keys


def _need_entry(session, version_id: int, key: str, kind: str) -> None:
    entry = get_entry(session, version_id, key)
    if entry is None or (kind and entry.kind != kind):
        raise BadAnswer("That answer does not fit this question.")


def _apply_conflict(
    session, version_id: int, question, key: str, label: str, run
) -> tuple[list[dict], dict]:
    """Resolve the one conflict this question asked about."""
    evidence = question.evidence if isinstance(question.evidence, dict) else {}
    if evidence.get("origin") != "conflict":
        raise BadAnswer("That answer does not fit this question.")
    scope = set(question.affects or [])
    if evidence.get("entry_key"):
        scope.add(evidence["entry_key"])
    if key not in scope:
        raise BadAnswer("That answer does not fit this question.")
    entry = get_entry(session, version_id, key)
    if entry is None:
        raise BadAnswer("That answer does not fit this question.")
    if entry.confidence != "conflicting":
        raise BadAnswer("That conflict is already resolved.")
    sources = list(entry.sources) if isinstance(entry.sources, list) else []
    sources.append({"type": "owner_answer", "text": label})
    details = dict(entry.details) if isinstance(entry.details, dict) else {}
    upsert_entry(
        session,
        version_id,
        key,
        entry.kind,
        entry.title,
        entry.meaning,
        details,
        "confirmed",
        sources,
        "The owner picked this side.",
    )
    retested: dict = {}
    if run is not None:
        from charie.learner.steps import recipes as recipes_step

        tables = _retest_tables(session, version_id, sorted(scope))
        retested = recipes_step.retest_affected(session, version_id, tables, run)
    return [{"entry": key, "before": "conflicting", "after": "confirmed"}], retested


def apply_answer(session, question_id: int, payload: dict, run, time_zone: str) -> dict:
    """Apply one answer; returns the id, status and what changed.

    Locks the question row, so two answers serialize: the same answer
    twice is idempotent, a different answer to an answered question
    raises AnswerConflict. Unknown questions raise AnswerNotFound,
    unusable answers raise BadAnswer.
    """
    question = session.scalar(
        select(OwnerQuestion).where(OwnerQuestion.id == question_id).with_for_update()
    )
    if question is None:
        raise AnswerNotFound("That question is gone.")
    option_id = payload.get("option_id") if isinstance(payload, dict) else None
    text = payload.get("text") if isinstance(payload, dict) else None
    has_option = isinstance(option_id, str) and option_id.strip() != ""
    has_text = isinstance(text, str) and text.strip() != ""
    if has_option == has_text:
        raise BadAnswer("Send exactly one of option_id or text.")
    previous_option = payload.get("previous_option_id") if isinstance(payload, dict) else None
    previous_text = payload.get("previous_text") if isinstance(payload, dict) else None
    has_prev_option = isinstance(previous_option, str) and previous_option.strip() != ""
    has_prev_text = isinstance(previous_text, str) and previous_text.strip() != ""
    if has_prev_option and has_prev_text:
        raise BadAnswer("Send exactly one of previous_option_id or previous_text.")
    if has_prev_option:
        prev: dict | None = {"option_id": previous_option.strip()}
    elif has_prev_text:
        prev = {"text": previous_text.strip()}
    else:
        prev = None
    options = {
        option.get("id"): option
        for option in (question.options or [])
        if isinstance(option, dict) and option.get("id")
    }
    if has_option and option_id not in options:
        raise BadAnswer("That answer does not fit this question.")
    new = {"option_id": option_id} if has_option else {"text": text.strip()}
    if question.status == "answered":
        stored = _core(question.answer)
        if stored == new:
            return {"id": question.id, "status": question.status, "idempotent": True}
        if prev is None or stored != prev:
            raise AnswerConflict("This question was already answered with a different answer.")
    draft = get_or_create_draft(session, "owner_edit")
    version_id = draft.id
    applied: list[dict] = []
    retested: dict = {}
    todo_id = None
    if has_text:
        todo_id = add_learner_todo(
            session,
            "correction",
            text.strip(),
            {
                "question_id": question.id,
                "topic": question.topic,
                "origin": (question.evidence or {}).get("origin", ""),
            },
        )
    else:
        option = options[option_id]
        proposal = option.get("proposal") if isinstance(option.get("proposal"), dict) else {}
        label = option.get("label") or ""
        if "calendar" in proposal:
            applied, retested = _apply_calendar(session, version_id, proposal, run)
        elif "default" in proposal:
            applied, keys = _apply_default(session, version_id, proposal, label)
            if keys and run is not None:
                from charie.learner.steps import recipes as recipes_step

                retested = recipes_step.retest_affected(session, version_id, keys, run)
        elif "metric" in proposal:
            key = proposal["metric"] or ""
            _need_entry(session, version_id, key, "metric")
            if run is not None:
                from charie.learner.steps import recipes as recipes_step

                tables = _retest_tables(session, version_id, [key])
                retested = recipes_step.retest_affected(session, version_id, tables, run)
            applied = [{"entry": key}]
        elif "entry" in proposal:
            key = proposal["entry"] or ""
            applied, retested = _apply_conflict(session, version_id, question, key, label, run)
        else:
            raise BadAnswer("That answer does not fit this question.")
    question.answer = {
        **new,
        "previous": _core(question.answer),
        "applied": applied,
        "retested": retested,
        "todo_id": todo_id,
        "at": _now(),
    }
    question.status = "answered"
    question.answered_at = datetime.now(UTC)
    session.flush()
    from charie.learner.events import add_event
    from charie.learner.runs import active_run

    active = active_run(session)
    if active is not None:
        add_event(
            session,
            active.id,
            "found",
            f"Applied your answer to “{question.topic}”.",
            step="owner_questions",
            details={"question_id": question.id, "retested": retested},
        )
    return {"id": question.id, "status": question.status, "applied": applied, "retested": retested}
