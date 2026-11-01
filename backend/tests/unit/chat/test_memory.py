"""Memories across chats: extract, save, use, switch off (P11.5)."""

from datetime import UTC, datetime

from charie.chat import memory as memory_module
from charie.chat.memory import (
    extract_and_save_memories,
    memories_for_prompt,
    normalize_memory_text,
)
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Chat, Memory, Message


def _user(db_session, text="For me, sales means without delivery fees.", status="done"):
    chat = Chat(title="Weekend vs weekday sales")
    db_session.add(chat)
    db_session.flush()
    message = Message(
        chat_id=chat.id,
        role="user",
        text_=text,
        status=status,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(message)
    db_session.commit()
    return message


def _fake(monkeypatch, *replies: dict) -> FakeAi:
    fake = FakeAi()
    for reply in replies:
        fake.reply("extract_memories", reply)
    monkeypatch.setattr(
        memory_module,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    return fake


def _extract(text="For me, sales means without delivery fees.", kind="meaning", replaces=None):
    return {
        "memories": [
            {"text": text, "kind": kind, "replaces": replaces or []},
        ]
    }


def test_a_stated_preference_is_saved(db_session, monkeypatch) -> None:
    """One lasting preference becomes one active memory."""
    message = _user(db_session)
    _fake(monkeypatch, _extract())
    extract_and_save_memories(db_session, message)
    rows = db_session.query(Memory).all()
    assert len(rows) == 1
    assert rows[0].text_ == "For me, sales means without delivery fees."
    assert rows[0].kind == "meaning"
    assert rows[0].source_chat_id == message.chat_id
    assert rows[0].active is True
    assert memories_for_prompt(db_session) == ["For me, sales means without delivery fees."]


def test_the_same_text_is_not_saved_twice(db_session, monkeypatch) -> None:
    """Case, spaces and a final full stop don't make a new memory."""
    message = _user(db_session)
    _fake(monkeypatch, _extract("  for me, SALES means without delivery fees. "))
    extract_and_save_memories(db_session, message)
    assert db_session.query(Memory).count() == 1


def test_a_replacing_memory_turns_the_old_one_off(db_session, monkeypatch) -> None:
    """The replaces id deactivates the older memory."""
    message = _user(db_session)
    _fake(monkeypatch, _extract())
    extract_and_save_memories(db_session, message)
    old_id = db_session.query(Memory).one().id
    second = _user(db_session, "For me, sales means with delivery fees.")
    _fake(monkeypatch, _extract("For me, sales means with delivery fees.", replaces=[old_id]))
    extract_and_save_memories(db_session, second)
    assert db_session.get(Memory, old_id).active is False
    assert memories_for_prompt(db_session) == ["For me, sales means with delivery fees."]


def test_a_number_not_in_the_message_is_rejected(db_session, monkeypatch) -> None:
    """The AI may not invent numbers the owner never typed."""
    message = _user(db_session)
    _fake(monkeypatch, _extract("Show money in thousands, like $96.2K."))
    extract_and_save_memories(db_session, message)
    assert db_session.query(Memory).count() == 0


def test_short_and_long_texts_are_rejected(db_session, monkeypatch) -> None:
    """Below 3 and above 200 characters never save."""
    message = _user(db_session)
    _fake(monkeypatch, {"memories": [{"text": "ok", "kind": "other", "replaces": []}]})
    extract_and_save_memories(db_session, message)
    _fake(monkeypatch, {"memories": [{"text": "x" * 201, "kind": "other", "replaces": []}]})
    extract_and_save_memories(db_session, message)
    assert db_session.query(Memory).count() == 0


def test_a_meaning_memory_adds_a_learner_to_do_item(db_session, monkeypatch) -> None:
    """Meaning changes land on the learner's to-check list."""
    from charie.shared.tables.questions import LearnerTodo

    message = _user(db_session)
    _fake(monkeypatch, _extract())
    extract_and_save_memories(db_session, message)
    todos = db_session.query(LearnerTodo).all()
    assert len(todos) == 1
    assert todos[0].kind == "meaning_change"
    assert todos[0].text_ == "The user says: For me, sales means without delivery fees."
    assert todos[0].details["chat_id"] == message.chat_id
    assert todos[0].details["message_id"] == message.id
    assert todos[0].details["words"] == message.text_


def test_memory_off_saves_nothing_and_gives_nothing(db_session, monkeypatch) -> None:
    """With the switch off, extraction skips and the prompt gets nothing."""
    from charie.shared.settings import set_setting

    set_setting(db_session, "memory_on", False)
    message = _user(db_session)
    _fake(monkeypatch, _extract())
    extract_and_save_memories(db_session, message)
    assert db_session.query(Memory).count() == 0
    assert memories_for_prompt(db_session) == []


def test_remember_false_saves_nothing(db_session, monkeypatch) -> None:
    """Test runs never trigger extraction; only done user messages do."""
    from charie.chat.analyst.context import RunState
    from charie.chat.analyst.runner import _extract_after_done

    assert RunState().remember is True
    assert RunState(remember=False).remember is False
    thinking = _user(db_session, status="thinking")
    _fake(monkeypatch, _extract(), _extract())
    extract_and_save_memories(db_session, thinking)
    assert db_session.query(Memory).count() == 0
    # The runner gate: no extraction without remember, even when done.
    done_user = _user(db_session)
    assistant = Message(
        chat_id=done_user.chat_id,
        role="assistant",
        text_="",
        status="done",
        mode="thinking",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(assistant)
    db_session.commit()
    _extract_after_done(assistant.id, RunState(remember=False))
    assert db_session.query(Memory).count() == 0
    _extract_after_done(assistant.id, RunState(remember=True))
    assert db_session.query(Memory).count() == 1


def test_only_messages_that_end_done_are_looked_at(db_session, monkeypatch) -> None:
    """A failed user message is ignored, and the assistant never is."""
    failed = _user(db_session, status="failed")
    _fake(monkeypatch, _extract())
    extract_and_save_memories(db_session, failed)
    assistant = db_session.query(Message).filter(Message.role == "assistant").first()
    if assistant is not None:
        extract_and_save_memories(db_session, assistant)
    assert db_session.query(Memory).count() == 0


def test_normalize_ignores_case_spaces_and_final_stop() -> None:
    assert normalize_memory_text("  For Me,  SALES. ") == "for me, sales"
