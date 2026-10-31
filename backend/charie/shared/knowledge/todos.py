"""The learner to-do list: small helper for corrections (P09.6 seeds it).

P09.7 processes open items; the chat correction endpoints arrive in P12.3.
"""

from charie.shared.tables.questions import LearnerTodo

TODO_KINDS = ("correction", "unknown_word", "new_metric", "meaning_change")


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
