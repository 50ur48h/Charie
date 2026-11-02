"""The understand step on the real database with queued AI replies (P10.4)."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from charie.chat.analyst.answer import NOT_SURE_TEXT, answer_question
from charie.chat.analyst.chat_context import ChatContext, ShownList, save_context
from charie.chat.analyst.understand import understand
from charie.shared.ai.client import AiClient
from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.knowledge import KbVersion
from tests.integration.chat.conftest import fake_understanding


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
    from charie.chat.chat_store import build_context

    return build_context(assistant.id)


def _reply(**overrides):
    reply = {
        "kind": "clear",
        "reading": "I read this as **delivered orders** for [p1].",
        "periods": [{"kind": "month", "number": 12}],
        "asks": [{"metric_key": "metric.delivered_orders"}],
        "filters": [],
        "defaults_used": [],
        "document_topics": [],
    }
    reply.update(overrides)
    return reply


def _bodies(db_session, message_id):
    from charie.shared.tables.chat import ThinkingEvent

    return db_session.scalars(
        select(ThinkingEvent.body)
        .where(ThinkingEvent.message_id == message_id)
        .order_by(ThinkingEvent.seq)
    ).all()


def test_understood_line_words(db_session, kb_mini, monkeypatch) -> None:
    """A good reply writes the understood line with the real dates."""
    ctx = _ctx_for(db_session, kb_mini, "Delivered orders in December 2025")
    fake_understanding(monkeypatch, _reply())
    understand(ctx)
    assert ctx.problems == []
    assert ctx.understanding.kind == "clear"
    assert (ctx.periods.periods[0].start.isoformat(), ctx.periods.periods[0].end.isoformat()) == (
        "2025-12-01",
        "2025-12-31",
    )
    bodies = _bodies(db_session, ctx.message_id)
    assert bodies[0].startswith("I read this as **delivered orders** for 1–31 Dec 2025.")


def test_retry_then_fallback_reading(db_session, kb_mini, monkeypatch) -> None:
    """Digits in the reading retry once, then the fallback reading wins."""
    from charie.shared.tables.chat import ThinkingEvent

    ctx = _ctx_for(db_session, kb_mini, "Delivered orders in December 2025")
    bad = _reply(reading="I read this as 42 delivered orders for [p1].")
    fake = fake_understanding(monkeypatch, bad, bad)
    understand(ctx)
    assert len([call for call in fake.calls if call[0] == "understand_question"]) == 2
    assert ctx.problems != []
    bodies = _bodies(db_session, ctx.message_id)
    assert any("I read this as Delivered orders for 1–31 Dec 2025." in body for body in bodies)
    titles = db_session.scalars(
        select(ThinkingEvent.title).where(ThinkingEvent.message_id == ctx.message_id)
    ).all()
    assert titles[0] == "Understood the question"


def test_dropped_filter_adds_note_line(db_session, kb_mini, monkeypatch) -> None:
    """An unknown filter value is dropped with its exact note."""
    ctx = _ctx_for(db_session, kb_mini, "Delivered orders in December 2025")
    bad = _reply(filters=[{"dimension_key": "dimension.restaurant_id", "values": ["Uptown"]}])
    fake_understanding(monkeypatch, bad, bad)
    understand(ctx)
    bodies = _bodies(db_session, ctx.message_id)
    assert any('I couldn\'t match "Uptown"' in body for body in bodies)
    assert ctx.understanding.filters == []


def test_first_call_not_already_running(db_session, kb_mini, monkeypatch) -> None:
    """The first AI call of a question never claims to be already running."""
    seen = []
    original_run = AiClient.run

    def _capture(self, job, inputs, form, **kwargs):
        seen.append(kwargs)
        return original_run(self, job, inputs, form, **kwargs)

    monkeypatch.setattr(AiClient, "run", _capture)
    ctx = _ctx_for(db_session, kb_mini, "Delivered orders in December 2025")
    fake_understanding(monkeypatch, _reply())
    understand(ctx)
    assert seen != []
    assert all(call.get("already_running") is False for call in seen)


def _seed_list(db_session, chat_id) -> None:
    """A chat that just saw a two-restaurant comparison."""
    save_context(
        db_session,
        chat_id,
        ChatContext(
            lists=[
                ShownList(
                    message_id=1,
                    title="Delivered orders by restaurant",
                    dimension="dimension.restaurant_id",
                    items=["Downtown", "Uptown"],
                )
            ]
        ),
    )
    db_session.commit()


def _follow_up_reply(**overrides):
    reply = _reply(
        kind="follow_up",
        reading="I read this as **delivered orders** for {ref1} for [p1].",
        asks=[{"metric_key": "metric.delivered_orders"}],
        list_refs=[
            {
                "words": "the second one",
                "position": 2,
                "dimension": "dimension.restaurant_id",
            }
        ],
    )
    reply.update(overrides)
    return reply


def test_thinking_line_names_the_item_and_its_list(db_session, kb_mini, monkeypatch) -> None:
    """A resolved follow-up filters to the listed restaurant and says so."""
    ctx = _ctx_for(db_session, kb_mini, "How did the second one do in December 2025?")
    _seed_list(db_session, ctx.chat_id)
    fake_understanding(monkeypatch, _follow_up_reply())
    understand(ctx)
    assert ctx.unresolved_follow_up is None
    assert ctx.understanding.filters[0].values == ["Uptown"]
    assert "for **Uptown**" in ctx.understanding.reading
    bodies = _bodies(db_session, ctx.message_id)
    assert bodies[-1] == (
        '"the second one" is Uptown, number 2 in "Delivered orders by restaurant".'
    )


def test_unresolved_reference_gives_the_not_sure_reply(db_session, kb_mini, monkeypatch) -> None:
    """A pointer at nothing shown answers not-sure, with status done and no rounds."""
    from charie.shared.tables.chat import Message, ThinkingEvent

    ctx = _ctx_for(db_session, kb_mini, "How did the ninth one do in December 2025?")
    _seed_list(db_session, ctx.chat_id)
    fake_understanding(
        monkeypatch, _follow_up_reply(list_refs=[{"words": "the ninth one", "position": 9}])
    )
    asyncio.run(answer_question(ctx))
    db_session.refresh(db_session.get(Message, ctx.message_id))
    message = db_session.get(Message, ctx.message_id)
    assert message.status == "done"
    assert message.answer["blocks"] == [{"type": "callout", "tone": "note", "text": NOT_SURE_TEXT}]
    titles = db_session.scalars(
        select(ThinkingEvent.title).where(ThinkingEvent.message_id == ctx.message_id)
    ).all()
    assert "Couldn't match the follow-up" in titles
    assert not any(title.startswith("Round ") for title in titles)


def test_empty_version_falls_back_without_ai_help(db_session, monkeypatch) -> None:
    """A version with no relevant keys still ends with a dated line."""
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.commit()
    ctx = _ctx_for(db_session, version.id, "Net sales?")
    fake_understanding(monkeypatch)
    understand(ctx)
    bodies = _bodies(db_session, ctx.message_id)
    assert any("Dec 2025" in body for body in bodies)
