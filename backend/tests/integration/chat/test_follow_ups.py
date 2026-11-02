"""Follow-up questions, resolved by code from the chat memory (P11.2).

No paid calls: the AI replies are queued fakes on the tiny knowledge,
and the chat memory is seeded the way the December answer would save
it. The four public follow-up questions run for real in Task 5, once
their fresh recordings are authorized.
"""

from datetime import UTC, datetime

from charie.chat.analyst.chat_context import ChatContext, Focus, ShownList, save_context
from charie.chat.analyst.understand import understand
from charie.chat.chat_store import build_context
from charie.shared.tables.chat import Chat, Message
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
    return build_context(assistant.id)


def _reply(**overrides):
    reply = {
        "kind": "follow_up",
        "reading": "I read this as **delivered orders** for [p1].",
        "periods": [],
        "asks": [],
        "filters": [],
        "defaults_used": [],
        "document_topics": [],
        "inherit": [],
        "list_refs": [],
        "period_shift": None,
    }
    reply.update(overrides)
    return reply


def test_the_second_one_resolves_to_the_right_restaurant(db_session, kb_mini, monkeypatch) -> None:
    """The second restaurant of the saved comparison becomes the filter."""
    ctx = _ctx_for(db_session, kb_mini, "How did the second one do in 2025?")
    save_context(
        db_session,
        ctx.chat_id,
        ChatContext(
            focus=Focus(
                message_id=1,
                question="Which restaurants sold most in 2025?",
                kind="clear",
                asks=[
                    {
                        "metric_key": "metric.delivered_orders",
                        "new_metric": "",
                        "split_by": ["dimension.restaurant_id"],
                        "top_n": None,
                    }
                ],
                filters=[],
                periods=[
                    {
                        "label": "p1",
                        "expression": {"kind": "year", "year": 2025},
                        "start": "2025-01-01",
                        "end": "2025-12-31",
                        "text": "1 Jan - 31 Dec 2025",
                    }
                ],
            ),
            lists=[
                ShownList(
                    message_id=1,
                    title="Delivered orders by restaurant",
                    dimension="dimension.restaurant_id",
                    items=["Downtown", "Uptown", "Westside", "Northgate", "Eastend"],
                )
            ],
        ),
    )
    db_session.commit()
    fake_understanding(
        monkeypatch,
        _reply(
            reading="I read this as **delivered orders** for {ref1} for [p1].",
            periods=[{"kind": "year", "year": 2025}],
            inherit=["asks"],
            list_refs=[
                {
                    "words": "the second one",
                    "position": 2,
                    "dimension": "dimension.restaurant_id",
                }
            ],
        ),
    )
    understand(ctx)
    assert ctx.unresolved_follow_up is None
    assert [ask.metric_key for ask in ctx.understanding.asks] == ["metric.delivered_orders"]
    assert [(filt.dimension_key, filt.values) for filt in ctx.understanding.filters] == [
        ("dimension.restaurant_id", ["Uptown"])
    ]
    assert ctx.understanding.reading == (
        "I read this as **delivered orders** for **Uptown** for [p1]."
    )
    assert (ctx.periods.periods[0].start.isoformat(), ctx.periods.periods[0].end.isoformat()) == (
        "2025-01-01",
        "2025-12-31",
    )


def test_same_for_last_year_moves_the_periods_back_a_year(db_session, kb_mini, monkeypatch) -> None:
    """The Q4 focus shifts to Q4 of the year before, keeping the ask."""
    ctx = _ctx_for(db_session, kb_mini, "Same for last year?")
    save_context(
        db_session,
        ctx.chat_id,
        ChatContext(
            focus=Focus(
                message_id=1,
                question="What were delivered orders in Q4 2025?",
                kind="clear",
                asks=[
                    {
                        "metric_key": "metric.delivered_orders",
                        "new_metric": "",
                        "split_by": [],
                        "top_n": None,
                    }
                ],
                filters=[],
                periods=[
                    {
                        "label": "p1",
                        "expression": {"kind": "quarter", "number": 4, "year": 2025},
                        "start": "2025-10-01",
                        "end": "2025-12-31",
                        "text": "1 Oct - 31 Dec 2025",
                    }
                ],
            )
        ),
    )
    db_session.commit()
    fake_understanding(
        monkeypatch,
        _reply(
            reading="I read this as **delivered orders** for last year.",
            inherit=["asks"],
            period_shift={"words": "last year", "unit": "year", "n": -1},
        ),
    )
    understand(ctx)
    assert ctx.unresolved_follow_up is None
    assert [ask.metric_key for ask in ctx.understanding.asks] == ["metric.delivered_orders"]
    assert [
        (period.start.isoformat(), period.end.isoformat()) for period in ctx.periods.periods
    ] == [("2024-10-01", "2024-12-31")]
