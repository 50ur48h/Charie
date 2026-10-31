"""The learner to-do list: small helper for corrections (P09.6 seeds it).

P09.7 processes open items; the chat correction endpoints arrive in P12.3.
"""

from charie.shared.tables.questions import LearnerTodo

TODO_KINDS = ("correction", "unknown_word", "new_metric", "meaning_change")

DISMISSED_BY_YOU = "Dismissed by you"


class TodoNotFound(LookupError):
    """No to-do with that id."""


def add_learner_todo(session, kind: str, text: str, details: dict | None = None) -> int:
    """Queue one open to-do; returns its id for the caller to reference."""
    if kind not in TODO_KINDS:
        raise ValueError(f"Todo kind must be one of {', '.join(TODO_KINDS)}.")
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Todo text must not be empty.")
    row = LearnerTodo(kind=kind, text_=cleaned, details=dict(details or {}), status="open")
    session.add(row)
    session.flush()
    return row.id


def dismiss_todo(session, todo_id: int) -> object:
    """Dismiss one to-do as your own action; the entry itself never changes."""
    from datetime import UTC, datetime

    todo = session.get(LearnerTodo, todo_id)
    if todo is None:
        raise TodoNotFound(f"There is no to-do called {todo_id}.")
    if todo.status != "dismissed":
        todo.status = "dismissed"
        todo.result = DISMISSED_BY_YOU
        todo.done_at = datetime.now(UTC)
        session.flush()
    return todo
