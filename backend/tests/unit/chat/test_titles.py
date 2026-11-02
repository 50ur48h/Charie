"""Chat titles after the first done answer (P11.6).

Fake AI throughout; no paid calls. The sidebar refetch is a chat-page
test; here the screen contract is the saved title on the chat row.
"""

import time
from datetime import UTC, datetime

from charie.chat import titles as titles_module
from charie.chat.analyst import answer as answer_module
from charie.chat.analyst.dates import PeriodSet
from charie.chat.analyst.understand import Understanding
from charie.chat.chat_store import _cut_title, build_context
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Chat, Message

FIRST_QUESTION = "What was the delivered order amount in December 2025?"


def _chat_with_answer(db_session):
    """An auto-titled chat with one done assistant message."""
    from charie.shared.tables.knowledge import KbVersion

    version = KbVersion(number=3, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()
    chat = Chat(title="New chat", private=False)
    db_session.add(chat)
    db_session.flush()
    kb_version_id = version.id
    db_session.add(
        Message(
            chat_id=chat.id,
            role="user",
            text_=FIRST_QUESTION,
            status="done",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    )
    assistant = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="done",
        kb_version_id=kb_version_id,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        answer={
            "message_id": 0,
            "kb_version": 3,
            "data_through": "2025-12-31",
            "blocks": [
                {
                    "type": "reading",
                    "text": "I read this as the delivered order amount for December.",
                }
            ],
        },
    )
    db_session.add(assistant)
    db_session.commit()
    assert chat.title == "New chat"
    chat.title = _cut_title(FIRST_QUESTION)
    db_session.commit()
    return chat, assistant


def _fake_title(monkeypatch, title):
    fake = FakeAi()
    fake.reply("name_chat", {"title": title})
    monkeypatch.setattr(
        titles_module,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )


def _title(db_session, chat_id):
    db_session.expire_all()
    return db_session.get(Chat, chat_id).title


def test_names_a_new_chat_after_its_first_answer(db_session, monkeypatch) -> None:
    """The AI's good title replaces the automatic one."""
    chat, assistant = _chat_with_answer(db_session)
    _fake_title(monkeypatch, "December delivery review")
    titles_module.name_chat_if_new(db_session, chat, assistant)
    assert _title(db_session, chat.id) == "December delivery review"


def test_keeps_a_title_the_user_changed(db_session, monkeypatch) -> None:
    """A renamed chat is never touched, even with a good title queued."""
    chat, assistant = _chat_with_answer(db_session)
    chat.title = "My December"
    db_session.commit()
    _fake_title(monkeypatch, "December delivery review")
    titles_module.name_chat_if_new(db_session, chat, assistant)
    assert _title(db_session, chat.id) == "My December"


def test_rejects_a_title_over_6_words(db_session, monkeypatch) -> None:
    """Seven words keep the automatic title."""
    chat, assistant = _chat_with_answer(db_session)
    _fake_title(monkeypatch, "A very long title with far too many words")
    titles_module.name_chat_if_new(db_session, chat, assistant)
    assert _title(db_session, chat.id) == _cut_title(FIRST_QUESTION)


def test_rejects_a_title_with_digits(db_session, monkeypatch) -> None:
    """The AI may not type digits, even a year."""
    chat, assistant = _chat_with_answer(db_session)
    _fake_title(monkeypatch, "December 2025 sales review")
    titles_module.name_chat_if_new(db_session, chat, assistant)
    assert _title(db_session, chat.id) == _cut_title(FIRST_QUESTION)


def test_a_timeout_keeps_the_automatic_title(db_session, monkeypatch) -> None:
    """A slow naming call never renames and never retries."""

    class SlowAi:
        def run(self, *args, **kwargs):
            time.sleep(2)
            return titles_module.ChatTitle(title="December delivery review")

    monkeypatch.setattr(titles_module, "get_ai", lambda: SlowAi())
    monkeypatch.setattr(titles_module, "TITLE_TIMEOUT_SECONDS", 0.05)
    chat, assistant = _chat_with_answer(db_session)
    titles_module.name_chat_if_new(db_session, chat, assistant)
    assert _title(db_session, chat.id) == _cut_title(FIRST_QUESTION)


def test_title_rules_reject_screen_text_problems() -> None:
    """Quotes, extra lines, length and a final stop never become titles."""
    assert titles_module._title_ok("December delivery review")
    assert not titles_module._title_ok("December")
    assert not titles_module._title_ok("A very long title with far too many words in it")
    assert not titles_module._title_ok("December 2025 sales review")
    assert not titles_module._title_ok('The "December" review')
    assert not titles_module._title_ok("December delivery review.")
    assert not titles_module._title_ok("December delivery\nreview")
    assert not titles_module._title_ok("x" * 61)


def test_name_chat_false_skips_naming(db_session, monkeypatch) -> None:
    """Test runs never rename: the flag gates the done-answer hook."""
    chat = Chat(title="New chat", private=False)
    db_session.add(chat)
    db_session.flush()
    db_session.add(
        Message(
            chat_id=chat.id,
            role="user",
            text_=FIRST_QUESTION,
            status="done",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    )
    thinking = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="thinking",
        mode="thinking",
        started_at=datetime.now(UTC),
    )
    db_session.add(thinking)
    db_session.commit()
    chat.title = _cut_title(FIRST_QUESTION)
    db_session.commit()
    _fake_title(monkeypatch, "December delivery review")
    ctx = build_context(thinking.id)
    assert ctx is not None
    ctx.name_chat = False
    ctx.understanding = Understanding(kind="clear", reading="I read this as December.")
    ctx.periods = PeriodSet()
    answer_module._save_blocks(ctx, [{"type": "text", "paragraphs": []}], [])
    assert _title(db_session, chat.id) == _cut_title(FIRST_QUESTION)
    ctx.name_chat = True
    answer_module._save_blocks(ctx, [{"type": "text", "paragraphs": []}], [])
    assert _title(db_session, chat.id) == "December delivery review"
