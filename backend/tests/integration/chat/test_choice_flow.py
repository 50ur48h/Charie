"""Answering a quick question continues the original question (P11.3).

Fake AI throughout; no paid calls. The continuation proof is the
server's doing: the user message keeps the saved option label (never
the client text), the next understanding reads through the waiting
quick question, and the wait clears when the answer finishes.
"""

import asyncio

import pytest

from charie.chat.analyst import enough as enough_module
from charie.chat.analyst import review as review_module
from charie.chat.analyst import write as write_module
from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.chat_context import load_context
from charie.chat.analyst.stream import FEEDS, MessageFeed
from charie.chat.chat_store import ask_question, build_context
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.errors import ApiError
from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.knowledge import KbEntry, KbVersion
from tests.integration.chat.conftest import fake_understanding


def _kb_version(db_session) -> int:
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="metric.delivered_orders",
            kind="metric",
            title="Delivered orders",
            meaning="Orders handed to the customer.",
            details={},
            confidence="checked",
            sources=[],
        )
    )
    db_session.commit()
    return version.id


def _chat(db_session) -> int:
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.commit()
    return chat.id


def _ask(db_session, chat_id, text, choice=None):
    _, assistant = ask_question(db_session, chat_id, text, "thinking", choice)
    db_session.commit()
    return build_context(assistant.id)


def _choice_reply():
    return {
        "kind": "vague_no_default",
        "reading": "I read this as best restaurants for [p1].",
        "periods": [{"kind": "month", "number": 12}],
        "asks": [],
        "filters": [],
        "defaults_used": [],
        "document_topics": [],
        "choice": {
            "text": "How should I rank them?",
            "options": [
                {"id": "by_net_sales", "label": "By net sales"},
                {"id": "by_growth", "label": "By growth"},
            ],
        },
        "meanings": [],
    }


def _clear_reply():
    return {
        "kind": "clear",
        "reading": "I read this as delivered orders by growth for [p1].",
        "periods": [{"kind": "month", "number": 12}],
        "asks": [],
        "filters": [],
        "defaults_used": [],
        "document_topics": [],
    }


def _patch(monkeypatch, module, job, replies) -> FakeAi:
    fake = FakeAi()
    for reply in replies:
        fake.reply(job, reply)
    monkeypatch.setattr(
        module,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    return fake


def _answer_done(monkeypatch) -> None:
    """Fake the downstream jobs so a continued answer finishes."""
    _patch(monkeypatch, enough_module, "check_enough", [{"enough": True, "missing": ""}])
    _patch(
        monkeypatch,
        review_module,
        "review_answer",
        [{"verdict": "good", "fixes": [], "needs_more_data": False, "missing_data": ""}],
    )
    _patch(
        monkeypatch,
        write_module,
        "write_answer",
        [
            {
                "blocks": [
                    {
                        "type": "text",
                        "sentences": [
                            {
                                "kind": "fact",
                                "text": "Delivered orders were [n1].",
                                "proof": [],
                                "starts_paragraph": True,
                            }
                        ],
                    }
                ]
            }
        ],
    )


def _needs_choice(db_session, monkeypatch, chat_id):
    ctx = _ask(db_session, chat_id, "Which are our best restaurants?")
    fake_understanding(monkeypatch, _choice_reply())
    asyncio.run(answer_question(ctx))
    assert db_session.get(Message, ctx.message_id).status == "needs_choice"
    return ctx


def test_picking_an_option_continues_the_original_question(db_session, monkeypatch) -> None:
    """The pick answers through the wait, finishes done, and clears it."""
    chat_id = _chat(db_session)
    _kb_version(db_session)
    _needs_choice(db_session, monkeypatch, chat_id)
    ctx = _ask(db_session, chat_id, "By growth", choice="by_growth")
    fake_understanding(monkeypatch, _clear_reply())
    _answer_done(monkeypatch)
    asyncio.run(answer_question(ctx))
    assert db_session.get(Message, ctx.message_id).status == "done"
    assert load_context(db_session, chat_id).pending_choice is None


def test_the_label_becomes_the_user_message(db_session, monkeypatch) -> None:
    """The server keeps its saved label, never the client text."""
    chat_id = _chat(db_session)
    _kb_version(db_session)
    _needs_choice(db_session, monkeypatch, chat_id)
    user_id = db_session.scalar(
        __import__("sqlalchemy")
        .select(Message.id)
        .where(Message.chat_id == chat_id, Message.role == "user")
        .order_by(Message.id.desc())
    )
    ctx = _ask(db_session, chat_id, "client text is ignored", choice="by_growth")
    user_message = db_session.get(Message, ctx.message_id - 1)
    assert user_message.id != user_id
    assert user_message.text_ == "By growth"


def test_a_second_pick_gets_choice_not_waiting(db_session, monkeypatch) -> None:
    """Once the answer finishes, the wait is gone."""
    chat_id = _chat(db_session)
    _kb_version(db_session)
    _needs_choice(db_session, monkeypatch, chat_id)
    ctx = _ask(db_session, chat_id, "By growth", choice="by_growth")
    fake_understanding(monkeypatch, _clear_reply())
    _answer_done(monkeypatch)
    asyncio.run(answer_question(ctx))
    with pytest.raises(ApiError) as caught:
        _ask(db_session, chat_id, "By growth", choice="by_growth")
    assert caught.value.code == "choice_not_waiting"


def test_an_unknown_id_gets_unknown_choice(db_session, monkeypatch) -> None:
    """A made-up option id is refused."""
    chat_id = _chat(db_session)
    _kb_version(db_session)
    _needs_choice(db_session, monkeypatch, chat_id)
    with pytest.raises(ApiError) as caught:
        _ask(db_session, chat_id, "By everything", choice="by_everything")
    assert caught.value.code == "unknown_choice"


def test_reconnecting_re_sends_the_choice(db_session, monkeypatch) -> None:
    """The choice event sits in the live feed, so a reconnect replays it."""
    chat_id = _chat(db_session)
    _kb_version(db_session)
    ctx = _ask(db_session, chat_id, "Which are our best restaurants?")
    FEEDS[ctx.message_id] = MessageFeed()
    try:
        fake_understanding(monkeypatch, _choice_reply())
        asyncio.run(answer_question(ctx))
        events = [item for item in FEEDS[ctx.message_id].events_after(0)]
        choices = [item for item in events if item.event == "choice"]
        assert len(choices) == 1
        assert choices[0].data["options"][0]["id"] == "by_net_sales"
        assert events[-1].event == "done"
        assert events[-1].data["status"] == "needs_choice"
    finally:
        FEEDS.pop(ctx.message_id, None)
