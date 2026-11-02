"""The memories addresses on the real API (P11.5)."""

from datetime import UTC, datetime

from charie.shared.tables.chat import Chat, Memory
from tests.conftest import log_in


def _seed(db_session):
    chat = Chat(title="Weekend vs weekday sales")
    db_session.add(chat)
    db_session.flush()
    first = Memory(
        text_='For me, "sales" means without delivery fees.',
        kind="meaning",
        source_chat_id=chat.id,
        active=True,
        created_at=datetime(2025, 10, 12, tzinfo=UTC),
    )
    second = Memory(
        text_="I mostly care about the Austin restaurants.",
        kind="focus",
        source_chat_id=None,
        active=True,
        created_at=datetime(2025, 10, 20, tzinfo=UTC),
    )
    db_session.add(first)
    db_session.add(second)
    db_session.commit()
    return chat, first, second


def test_list_memories_shows_source_and_keeps_newest_first(chat_client, db_session) -> None:
    """The list carries the chat title or the deleted-chat words."""
    log_in(chat_client)
    _, first, _ = _seed(db_session)
    listed = chat_client.get("/api/memories").json()
    assert [(row["id"], row["text"], row["source"]) for row in listed] == [
        (
            first.id + 1,
            "I mostly care about the Austin restaurants.",
            "From a deleted chat · 20 Oct",
        ),
        (
            first.id,
            'For me, "sales" means without delivery fees.',
            'From the chat "Weekend vs weekday sales" · 12 Oct',
        ),
    ]


def test_delete_memory_forgets_one(chat_client, db_session) -> None:
    """Deleting deactivates the memory; a second delete is 404."""
    log_in(chat_client)
    _, first, _ = _seed(db_session)
    deleted = chat_client.delete(f"/api/memories/{first.id}")
    assert deleted.status_code == 200
    db_session.expire_all()
    assert db_session.get(Memory, first.id).active is False
    assert [row["id"] for row in chat_client.get("/api/memories").json()] == [first.id + 1]
    missing = chat_client.delete(f"/api/memories/{first.id}")
    assert missing.status_code == 404


def test_delete_unknown_memory_is_404(chat_client) -> None:
    log_in(chat_client)
    assert chat_client.delete("/api/memories/1000000").status_code == 404


def test_clear_memories_forgets_everything(chat_client, db_session) -> None:
    """Forget everything deactivates every active memory."""
    log_in(chat_client)
    _seed(db_session)
    cleared = chat_client.delete("/api/memories")
    assert cleared.status_code == 200
    assert chat_client.get("/api/memories").json() == []
    assert db_session.query(Memory).filter(Memory.active.is_(True)).count() == 0
