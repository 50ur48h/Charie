"""The learner to-do list: work through open corrections (P09.7).

Each open item becomes a tested proposal, an owner question or an
explained dismissal. A correction to a metric retests the recipe: when
it still checks out the item is done, when it fails the owner gets a
question with the originating words. Anything without a checkable path
gets an explicit result instead of silence. Items commit one by one, so
a retry never duplicates a question and never loses an item.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from charie.learner.steps.base import StepContext, run_query
from charie.shared.knowledge.questions import QuestionTopic, make_owner_questions
from charie.shared.knowledge.store import get_entry
from charie.shared.settings import get_setting
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import LearnerTodo, OwnerQuestion

RUN_SOURCES = {"first": "learning", "refresh": "refresh", "nightly": "nightly"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _finish(todo: LearnerTodo, result: str) -> None:
    """Done with its reason kept; the caller commits."""
    todo.status = "done"
    todo.result = result
    todo.done_at = datetime.now(UTC)


def _retest_metric(session, version_id: int, key: str, run) -> dict:
    """Retest one metric's recipe; empty without a table to check."""
    from charie.learner.steps import recipes as recipes_step

    entry = get_entry(session, version_id, key)
    details = entry.details if entry is not None and isinstance(entry.details, dict) else {}
    if not details.get("table"):
        return {}
    return recipes_step.retest_affected(session, version_id, [details["table"]], run)


def _ask(session, version_id, todo, topic, run, time_zone, source) -> bool:
    """Ask the owner; done only when the question is committed."""
    created, _ = make_owner_questions(session, version_id, [topic], run, time_zone, source)
    if not created:
        return False
    asked = session.get(OwnerQuestion, created[0])
    _finish(todo, f"Asked you: {asked.title if asked else topic.topic}.")
    session.flush()
    return True


def _words(todo: LearnerTodo, details: dict) -> str:
    """The originating words, from details or the todo text."""
    words = details.get("words")
    if isinstance(words, str) and words.strip():
        return words.strip()
    return (todo.text_ or "").strip()


def _handle_correction(session, version_id, todo, details, run, time_zone, source) -> bool:
    """Retest metrics, ask about the rest, explain what can't be checked."""
    key = details.get("key") or ""
    entry = get_entry(session, version_id, key) if key else None
    if entry is None and not details.get("question_id"):
        _finish(todo, "The entry is gone, so there is nothing to check.")
        session.flush()
        return True
    if entry is not None and entry.kind == "metric":
        outcome = _retest_metric(session, version_id, key, run)
        if outcome and all(outcome.values()):
            _finish(todo, f"{entry.title} still checks out after retesting.")
            session.flush()
            return True
        if outcome:
            return _ask(
                session,
                version_id,
                todo,
                QuestionTopic(
                    origin="todo",
                    topic=f"How to fix {entry.title}",
                    entry_key=key,
                    affects=(key,),
                    metric_key=key,
                    context={"words": _words(todo, details), "todo_id": todo.id},
                ),
                run,
                time_zone,
                source,
            )
        _finish(todo, "Charie couldn't re-check this yet; it stays open for the next run.")
        session.flush()
        return False
    title = entry.title if entry is not None else (todo.text_ or "this")
    return _ask(
        session,
        version_id,
        todo,
        QuestionTopic(
            origin="todo",
            topic=f"What should “{title}” mean",
            entry_key=key,
            affects=(key,) if key else (),
            context={"words": _words(todo, details), "todo_id": todo.id},
        ),
        run,
        time_zone,
        source,
    )


def _handle_word(session, version_id, todo, details, run, time_zone, source, verb) -> bool:
    """An unknown word or a new metric becomes a question with its words."""
    word = details.get("word") or details.get("name") or (todo.text_ or "").strip()
    if not word:
        _finish(todo, "There were no words to check, so this was set aside.")
        session.flush()
        return True
    return _ask(
        session,
        version_id,
        todo,
        QuestionTopic(
            origin="todo",
            topic=f"{verb} “{word}”",
            context={"words": word, "todo_id": todo.id},
        ),
        run,
        time_zone,
        source,
    )


def _handle_meaning_change(session, version_id, todo, details, run, time_zone, source) -> bool:
    """A proposed new meaning becomes a question; invalid ones are explained."""
    key = details.get("key") or ""
    proposed = details.get("proposed") or ""
    entry = get_entry(session, version_id, key) if key else None
    if entry is None or not proposed:
        _finish(todo, "The entry or the proposed meaning was missing, so this was set aside.")
        session.flush()
        return True
    if entry.kind == "default":
        from charie.shared.knowledge.defaults import tested_metric_keys, validate_default

        entry_details = entry.details if isinstance(entry.details, dict) else {}
        problems = validate_default(
            entry_details.get("word") or "", proposed, tested_metric_keys(session, version_id)
        )
        if problems:
            _finish(todo, f"That meaning doesn't fit: {problems[0]}")
            session.flush()
            return True
    return _ask(
        session,
        version_id,
        todo,
        QuestionTopic(
            origin="todo",
            topic=f"What should “{entry.title}” mean now",
            entry_key=key,
            affects=(key,),
            context={"words": _words(todo, details), "proposed": proposed, "todo_id": todo.id},
        ),
        run,
        time_zone,
        source,
    )


def _handle_one(session, version_id, todo, run, time_zone, source) -> bool:
    """One item to done, a question or an explicit result; False stays open."""
    details = todo.details if isinstance(todo.details, dict) else {}
    if todo.kind == "correction":
        return _handle_correction(session, version_id, todo, details, run, time_zone, source)
    if todo.kind == "unknown_word":
        return _handle_word(session, version_id, todo, details, run, time_zone, source, "What does")
    if todo.kind == "new_metric":
        return _handle_word(
            session, version_id, todo, details, run, time_zone, source, "What should"
        )
    if todo.kind == "meaning_change":
        return _handle_meaning_change(session, version_id, todo, details, run, time_zone, source)
    _finish(todo, "Charie doesn't handle this kind of to-do yet.")
    session.flush()
    return True


def handle_todos(ctx: StepContext) -> dict:
    """Work through every open to-do; returns done, questions and errors.

    Commits item by item: a retry never duplicates a question (same
    evidence stays asked) and never loses an item after a partial
    failure. Empty with no open items: no AI calls, no feed lines.
    """
    session = ctx.session
    todos = session.scalars(
        select(LearnerTodo).where(LearnerTodo.status == "open").order_by(LearnerTodo.id)
    ).all()
    if not todos:
        return {"done": 0, "questions": 0, "errors": []}
    time_zone = get_setting(session, "time_zone") or "UTC"
    source = run_id_source(session, ctx.run_id)

    def run(sql: str):
        return run_query(ctx, "todo", sql).rows

    summary: dict = {"done": 0, "questions": 0, "errors": []}
    for todo in todos:
        try:
            made = _handle_one(session, ctx.version_id, todo, run, time_zone, source)
            session.commit()
        except Exception as err:  # noqa: BLE001 (one bad item never blocks the rest)
            session.rollback()
            summary["errors"].append({"todo_id": todo.id, "error": str(err) or "error"})
            continue
        if made:
            summary["done"] += 1
            if todo.result and todo.result.startswith("Asked you:"):
                summary["questions"] += 1
    asked = [todo for todo in todos if todo.status == "done"]
    ctx.say(
        "found",
        f"Worked through {len(asked)} to-do(s): {summary['questions']} question(s) for you.",
    )
    return summary


def run_id_source(session, run_id: int | None) -> str:
    """The question source for this run's to-dos."""
    if run_id is None:
        return "learning"
    run = session.get(LearningRun, run_id)
    if run is None:
        return "learning"
    return RUN_SOURCES.get(run.kind or "", "learning")
