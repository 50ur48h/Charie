"""B021: cross-period comparisons need the same measure; else an honest finding."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

from charie.chat.analyst.helpers import new_number as new_number_module
from charie.chat.analyst.helpers.tasks import Task
from charie.chat.analyst.notebook import Notebook
from charie.shared.tables.chat import Chat, Message


def _message(db_session) -> Message:
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    message = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="thinking",
        started_at=datetime.now(UTC),
    )
    db_session.add(message)
    db_session.commit()
    return message


def _period(label, text, start, end):
    return SimpleNamespace(label=label, text=text, start=start, end=end)


def _written(sql, total):
    return SimpleNamespace(sql=sql, columns=["value"], rows=[[total]])


def _pair(sql, total, run_a, run_b):
    return (_written(sql, total), None, True, (run_a, run_b))


def _task():
    return Task(kind="new_number", new_metric="average order value", periods=["p1", "p2"])


SQL_2025 = (
    "SELECT SUM(o.total) AS value FROM shop.orders o "
    "WHERE o.created_at >= DATE '2025-12-01' AND o.created_at < DATE '2026-01-01'"
)
SQL_2024 = (
    "SELECT SUM(o.total) AS value FROM shop.orders o "
    "WHERE o.created_at >= DATE '2024-12-01' AND o.created_at < DATE '2025-01-01'"
)
SQL_CENTS = (
    "SELECT SUM(o.total_cents) AS value FROM shop.orders o "
    "WHERE o.created_at >= DATE '2025-12-01' AND o.created_at < DATE '2026-01-01'"
)


def _periods():
    return [
        _period("p1", "Dec 2025", date(2025, 12, 1), date(2025, 12, 31)),
        _period("p2", "Dec 2024", date(2024, 12, 1), date(2024, 12, 31)),
    ]


def test_mismatched_periods_save_no_change(db_session) -> None:
    """Different 2025/2024 measures: per-period numbers stay, no comparison."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    per_period = [_pair(SQL_CENTS, "39475.2", 11, 12), _pair(SQL_2024, "71.72", 13, 14)]
    new_number_module._save_new_totals(
        None,
        book,
        _task(),
        None,
        _periods(),
        per_period,
        1,
        "average order value",
        "new:average order value",
    )
    items = book.items()
    assert not any(item.kind == "number" and item.value.get("style") == "change" for item in items)
    findings = [item for item in items if item.kind == "finding"]
    assert len(findings) == 1
    assert findings[0].value["type"] == "couldnt_check"
    assert len([item for item in items if item.kind == "number"]) == 2


def test_matching_periods_save_change(db_session) -> None:
    """Same measure modulo dates: the comparison is saved, no finding."""
    message = _message(db_session)
    book = Notebook(db_session, message.id, message.chat_id)
    ctx = SimpleNamespace(log=SimpleNamespace(add=lambda *args, **kwargs: None))
    per_period = [_pair(SQL_2025, "200", 11, 12), _pair(SQL_2024, "100", 13, 14)]
    new_number_module._save_new_totals(
        ctx,
        book,
        _task(),
        None,
        _periods(),
        per_period,
        1,
        "average order value",
        "new:average order value",
    )
    items = book.items()
    assert any(item.kind == "number" and item.value.get("style") == "change" for item in items)
    assert not [item for item in items if item.kind == "finding"]
