"""Vague questions with no default ask one quick question (P11.3)."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from charie.chat.analyst.answer import NOT_SURE_TEXT, _save_blocks, answer_question
from charie.chat.analyst.chat_context import load_context
from charie.chat.analyst.understand import Understanding, check_understanding
from charie.chat.chat_store import build_context
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Chat, Message, ThinkingEvent
from charie.shared.tables.knowledge import KbEntry, KbVersion


def _kb_version(db_session) -> int:
    """One metric and one dimension; no defaults to settle."""
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
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="dimension.restaurant_id",
            kind="dimension",
            title="Restaurant",
            meaning="The shop that sold.",
            details={},
            confidence="checked",
            sources=[],
        )
    )
    db_session.commit()
    return version.id


def _ctx_for(db_session, kb_version, question):
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    user_message = Message(
        chat_id=chat.id,
        role="user",
        text_=question,
        status="done",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    assistant = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="thinking",
        mode="thinking",
        kb_version_id=kb_version,
        started_at=datetime.now(UTC),
    )
    db_session.add(user_message)
    db_session.add(assistant)
    db_session.commit()
    return build_context(assistant.id)


def _fake_ai(monkeypatch, *replies: dict) -> FakeAi:
    from charie.chat.analyst import understand as understand_module

    fake = FakeAi()
    for reply in replies:
        fake.reply("understand_question", reply)
    monkeypatch.setattr(
        understand_module,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    return fake


def _choice_reply(**overrides):
    reply = {
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
                {"id": "by_average_order", "label": "By average order"},
            ],
        },
        "meanings": [],
    }
    reply.update(overrides)
    return reply


def _kb():
    from datetime import date

    from charie.chat.analyst.kb_view import KbView

    entries = {"metric": {}, "dimension": {}, "default": {}, "name": {}}
    return KbView(entries, {}, date(2025, 12, 31), {})


def test_vague_question_with_no_default_asks_and_runs_no_rounds(db_session, monkeypatch) -> None:
    """A quick question stops the flow before round one."""
    ctx = _ctx_for(db_session, _kb_version(db_session), "Which are our best restaurants?")
    _fake_ai(monkeypatch, _choice_reply())
    asyncio.run(answer_question(ctx))
    assert ctx.stop_reason == "needs_choice"
    assert db_session.get(Message, ctx.message_id).status == "needs_choice"
    titles = db_session.scalars(
        select(ThinkingEvent.title).where(ThinkingEvent.message_id == ctx.message_id)
    ).all()
    assert "Asked you one quick question" in titles
    assert not any(title.startswith("Round ") for title in titles)


def test_choice_needs_2_to_4_options() -> None:
    one = _choice_reply()
    one["choice"]["options"] = one["choice"]["options"][:1]
    assert check_understanding(Understanding(**one), _kb()) != []
    six = _choice_reply()
    six["choice"]["options"] = six["choice"]["options"] * 2
    assert len(six["choice"]["options"]) == 6
    assert check_understanding(Understanding(**six), _kb()) != []
    assert check_understanding(Understanding(**_choice_reply()), _kb()) == []


def test_option_ids_must_be_different() -> None:
    reply = _choice_reply()
    reply["choice"]["options"][1]["id"] = "by_net_sales"
    problems = check_understanding(Understanding(**reply), _kb())
    assert any("different" in problem for problem in problems)


def test_digits_in_a_label_get_one_more_try() -> None:
    reply = _choice_reply()
    reply["choice"]["options"][0]["label"] = "Top 42"
    problems = check_understanding(Understanding(**reply), _kb())
    assert any("42" in problem for problem in problems)


def test_needs_choice_saves_the_choice_in_the_answer(db_session, monkeypatch) -> None:
    """The saved answer carries the choice; the message waits."""
    ctx = _ctx_for(db_session, _kb_version(db_session), "Which are our best restaurants?")
    _fake_ai(monkeypatch, _choice_reply())
    asyncio.run(answer_question(ctx))
    message = db_session.get(Message, ctx.message_id)
    assert message.status == "needs_choice"
    assert message.answer["blocks"] == []
    assert message.answer["choice"] == {
        "text": "How should I rank them?",
        "options": [
            {"id": "by_net_sales", "label": "By net sales"},
            {"id": "by_growth", "label": "By growth"},
            {"id": "by_average_order", "label": "By average order"},
        ],
    }
    assert NOT_SURE_TEXT not in str(message.answer)


def test_pending_choice_is_set_and_then_cleared(db_session, monkeypatch) -> None:
    """The wait is saved on needs_choice and gone after the next answer."""
    ctx = _ctx_for(db_session, _kb_version(db_session), "Which are our best restaurants?")
    _fake_ai(monkeypatch, _choice_reply())
    asyncio.run(answer_question(ctx))
    pending = load_context(db_session, ctx.chat_id).pending_choice
    assert pending is not None
    assert pending.message_id == ctx.message_id
    assert pending.question == "Which are our best restaurants?"
    assert pending.text == "How should I rank them?"
    assert [option["id"] for option in pending.options] == [
        "by_net_sales",
        "by_growth",
        "by_average_order",
    ]
    _save_blocks(ctx, [], [], status="done")
    assert load_context(db_session, ctx.chat_id).pending_choice is None
