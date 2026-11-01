"""About-an-answer and not-in-the-data replies, written by code (P11.6).

No paid calls: the earlier answer is seeded by hand, the about reply
uses no AI at all, and the quotes path fakes only the writer and the
reviewer. The four public follow-up questions run for real in Task 4,
once their fresh recordings are authorized.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select

from charie.chat.analyst import answer as answer_module
from charie.chat.analyst.about import (
    ABOUT_BODY,
    ABOUT_TITLE,
    NO_EARLIER_TEXT,
    NOTHING_TEXT,
    answer_about,
    answer_not_in_data,
)
from charie.chat.analyst.chat_context import ChatContext, Focus, load_context, save_context
from charie.chat.analyst.notebook import Notebook, NumberValue, QuoteValue
from charie.chat.analyst.understand import Understanding
from charie.chat.analyst.write import AnswerDraft
from charie.chat.chat_store import build_context
from charie.shared.tables.chat import Chat, Message, QueryRun, ThinkingEvent
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.sources import Document, DocumentSection


def _kb(db_session, number=3) -> int:
    version = KbVersion(number=number, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()
    for key, title, meaning in [
        ("metric.delivered_orders", "Delivered orders", "Orders handed to the customer."),
        ("metric.delivery_fees", "Delivery fees", "Fees for delivery orders."),
    ]:
        db_session.add(
            KbEntry(
                version_id=version.id,
                key=key,
                kind="metric",
                title=title,
                meaning=meaning,
                details={},
                confidence="checked",
                sources=[],
            )
        )
    db_session.commit()
    return version.id


def _chat(db_session):
    chat = Chat(title="New chat", private=False)
    db_session.add(chat)
    db_session.flush()
    return chat


def _user(db_session, chat_id, text):
    row = Message(
        chat_id=chat_id,
        role="user",
        text_=text,
        status="done",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _earlier(db_session, chat_id, version_id):
    """A done earlier answer with two numbers, runs and one Round line."""
    _user(db_session, chat_id, "What was the delivered order amount?")
    assistant = Message(
        chat_id=chat_id,
        role="assistant",
        text_="",
        status="done",
        kb_version_id=version_id,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        answer={
            "message_id": 0,
            "kb_version": 3,
            "data_through": "2025-12-31",
            "blocks": [
                {
                    "type": "text",
                    "paragraphs": [{"sentences": [{"kind": "fact", "text": "Done."}]}],
                },
                {
                    "type": "method",
                    "definitions": [],
                    "steps": [],
                    "queries": [],
                    "sources": [],
                },
            ],
        },
    )
    db_session.add(assistant)
    db_session.flush()
    assistant.answer["message_id"] = assistant.id
    run_one = QueryRun(
        message_id=assistant.id,
        purpose="Get delivered orders.",
        recipe_key="metric.delivered_orders",
        way="recipe",
        sql_text="SELECT 25064",
        status="ok",
    )
    run_two = QueryRun(
        message_id=assistant.id,
        purpose="Get delivery fees.",
        recipe_key="metric.delivery_fees",
        way="recipe",
        sql_text="SELECT 120.50",
        status="ok",
    )
    db_session.add(run_one)
    db_session.add(run_two)
    db_session.flush()
    book = Notebook(db_session, assistant.id, chat_id)
    book.add_number(
        "Delivered orders in 1-31 Dec 2025",
        NumberValue(value="25064", unit="count"),
        {
            "recipe_key": "metric.delivered_orders",
            "task": "recipe|metric.delivered_orders|",
            "query_run_ids": [run_one.id],
            "way": "recipe",
        },
    )
    book.add_number(
        "Delivery fees in 1-31 Dec 2025",
        NumberValue(value="120.50", unit="money", currency="USD"),
        {
            "recipe_key": "metric.delivery_fees",
            "task": "recipe|metric.delivery_fees|",
            "query_run_ids": [run_two.id],
            "way": "recipe",
        },
    )
    db_session.add(
        ThinkingEvent(
            message_id=assistant.id,
            seq=1,
            kind="step",
            status="done",
            title="Round 1: Get delivered orders.",
            body="",
            details={},
        )
    )
    db_session.commit()
    return assistant


def _current(db_session, chat, question, understanding):
    """The running question in an existing chat, with its understanding."""
    _user(db_session, chat.id, question)
    assistant = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="thinking",
        mode="thinking",
        started_at=datetime.now(UTC),
    )
    db_session.add(assistant)
    db_session.commit()
    ctx = build_context(assistant.id)
    assert ctx is not None
    ctx.understanding = understanding
    return ctx


def _about(about=None):
    return Understanding(
        kind="about_answer",
        reading="I read this as how I worked out my last answer.",
        periods=[],
        asks=[],
        filters=[],
        defaults_used=[],
        document_topics=[],
        about=about or [],
    )


def _not_in_data(missing="market share"):
    return Understanding(
        kind="not_in_data",
        reading="I read this as our market share.",
        periods=[],
        asks=[],
        filters=[],
        defaults_used=[],
        document_topics=[missing],
        missing=missing,
    )


def _saved(db_session, ctx):
    db_session.expire_all()
    saved = db_session.get(Message, ctx.message_id)
    assert saved is not None
    return saved


def _titles(db_session, message_id):
    return [
        line.title
        for line in db_session.scalars(
            select(ThinkingEvent)
            .where(ThinkingEvent.message_id == message_id)
            .order_by(ThinkingEvent.seq)
        ).all()
    ]


def test_about_one_number_shows_only_its_method(db_session) -> None:
    """One ref explains one number: its definition and its query only."""
    version_id = _kb(db_session)
    chat = _chat(db_session)
    earlier = _earlier(db_session, chat.id, version_id)
    ctx = _current(db_session, chat, "How did you get that number?", _about())
    ctx.understanding.about = [f"{earlier.id}:n1"]
    answer_about(ctx)
    saved = _saved(db_session, ctx)
    assert saved.status == "done"
    assert [block["type"] for block in saved.answer["blocks"]] == ["text", "method"]
    note = saved.answer["blocks"][0]["paragraphs"][0]["sentences"][0]
    assert note["kind"] == "note"
    assert note["text"].startswith("Here's how I worked out ")
    assert "Delivered orders in 1-31 Dec 2025" in note["text"]
    method = saved.answer["blocks"][1]
    assert method["definitions"] == ["Delivered orders: Orders handed to the customer."]
    assert [query["purpose"] for query in method["queries"]] == ["Get delivered orders."]
    assert saved.answer["kb_version"] == 3
    assert saved.answer["data_through"] == "2025-12-31"


def test_about_the_whole_answer_shows_the_full_method(db_session) -> None:
    """No refs explain the last answer: every number and query."""
    version_id = _kb(db_session)
    chat = _chat(db_session)
    _earlier(db_session, chat.id, version_id)
    ctx = _current(db_session, chat, "How did you get that?", _about())
    answer_about(ctx)
    saved = _saved(db_session, ctx)
    assert saved.status == "done"
    method = saved.answer["blocks"][1]
    assert method["definitions"] == [
        "Delivered orders: Orders handed to the customer.",
        "Delivery fees: Fees for delivery orders.",
    ]
    assert len(method["queries"]) == 2
    assert method["steps"] == ["Round 1: Get delivered orders."]
    note = saved.answer["blocks"][0]["paragraphs"][0]["sentences"][0]
    assert note["text"] == "Here's how I worked out my last answer."


def test_about_unknown_refs_explain_the_last_answer(db_session) -> None:
    """Refs that match nothing fall back to the whole last answer."""
    version_id = _kb(db_session)
    chat = _chat(db_session)
    _earlier(db_session, chat.id, version_id)
    ctx = _current(db_session, chat, "What about the other one?", _about())
    ctx.understanding.about = ["99999:n9"]
    answer_about(ctx)
    saved = _saved(db_session, ctx)
    assert saved.status == "done"
    assert saved.answer["blocks"][0]["paragraphs"][0]["sentences"][0]["text"] == (
        "Here's how I worked out my last answer."
    )
    assert len(saved.answer["blocks"][1]["definitions"]) == 2


def test_no_earlier_answer_gives_a_callout(db_session) -> None:
    """The first question can't ask about an earlier answer."""
    _kb(db_session)
    chat = _chat(db_session)
    ctx = _current(db_session, chat, "How did you get that?", _about())
    answer_about(ctx)
    saved = _saved(db_session, ctx)
    assert saved.status == "done"
    assert saved.answer["blocks"] == [{"type": "callout", "tone": "note", "text": NO_EARLIER_TEXT}]


def test_about_runs_no_rounds_and_leaves_the_context_alone(db_session) -> None:
    """An about reply saves no context and runs no rounds or checks."""
    version_id = _kb(db_session)
    chat = _chat(db_session)
    earlier = _earlier(db_session, chat.id, version_id)
    before = ChatContext(
        focus=Focus(
            message_id=earlier.id,
            question="What was the delivered order amount?",
            kind="clear",
            asks=[{"metric_key": "metric.delivered_orders"}],
            filters=[],
            periods=[],
        )
    )
    save_context(db_session, chat.id, before)
    db_session.commit()
    lines_before = len(db_session.scalars(select(ThinkingEvent)).all())
    ctx = _current(db_session, chat, "How did you get that number?", _about())
    assert load_context(db_session, chat.id) == before
    ctx.understanding.about = [f"{earlier.id}:n1"]
    answer_about(ctx)
    assert load_context(db_session, chat.id) == before
    assert _titles(db_session, ctx.message_id) == [ABOUT_TITLE]
    assert len(db_session.scalars(select(ThinkingEvent)).all()) == lines_before + 1


def test_not_in_data_without_quotes_is_written_by_code(db_session) -> None:
    """Nothing checked means a plain callout, no writer call."""
    version_id = _kb(db_session)
    chat = _chat(db_session)
    _earlier(db_session, chat.id, version_id)
    before = load_context(db_session, chat.id)
    ctx = _current(db_session, chat, "What is our market share?", _not_in_data())
    asyncio.run(answer_not_in_data(ctx, []))
    saved = _saved(db_session, ctx)
    assert saved.status == "done"
    assert saved.answer["blocks"][0] == {
        "type": "callout",
        "tone": "note",
        "text": "Your data doesn't have market share, so I can't work it out from the numbers.",
    }
    note = saved.answer["blocks"][1]["paragraphs"][0]["sentences"][0]
    assert note == {"kind": "note", "text": NOTHING_TEXT}
    assert load_context(db_session, chat.id) == before
    assert _titles(db_session, ctx.message_id) == ["Not in your data"]


def test_not_in_data_with_quotes_writes_from_checked_quotes(db_session, monkeypatch) -> None:
    """Checked quotes go through the writer; the method lists the document."""
    _kb(db_session)
    chat = _chat(db_session)
    ctx = _current(db_session, chat, "What is our market share?", _not_in_data())
    db_session.add(
        Document(
            file_name="policy.md",
            file_type="md",
            size_bytes=100,
            sha256="abc",
            status="learned",
        )
    )
    db_session.flush()
    document = db_session.scalars(select(Document)).one()
    db_session.add(
        DocumentSection(
            document_id=document.id,
            position=0,
            text_="Note: market share is not tracked here.",
        )
    )
    db_session.flush()
    section = db_session.scalars(select(DocumentSection)).one()
    book = Notebook(db_session, ctx.message_id, ctx.chat_id)
    book.add_quote(
        "Market share note",
        QuoteValue(
            text="market share is not tracked",
            document_id=document.id,
            document="policy.md",
            section_id=section.id,
            heading_path="",
            location="page 2",
        ),
    )
    db_session.commit()
    draft = {
        "blocks": [
            {
                "type": "text",
                "sentences": [
                    {
                        "kind": "fact",
                        "text": "The note says market share is not tracked [q1].",
                        "proof": ["q1"],
                        "starts_paragraph": True,
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(
        answer_module,
        "write_answer",
        lambda ctx, fixes=None: AnswerDraft.model_validate(draft),
    )
    monkeypatch.setattr(
        answer_module,
        "review_answer",
        lambda ctx, blocks: SimpleNamespace(
            verdict="good", fixes=[], needs_more_data=False, missing_data=""
        ),
    )
    asyncio.run(answer_not_in_data(ctx, []))
    saved = _saved(db_session, ctx)
    assert saved.status == "done"
    kinds = [block["type"] for block in saved.answer["blocks"]]
    assert kinds[0] == "reading"
    assert kinds[1] == "text"
    text = saved.answer["blocks"][1]["paragraphs"][0]["sentences"][0]["text"]
    assert "market share is not tracked" in text
    method = next(block for block in saved.answer["blocks"] if block["type"] == "method")
    assert method["sources"] == [
        {"document": "policy.md", "quote": "market share is not tracked", "location": "page 2"}
    ]


def test_thinking_lines_match_the_plan_words() -> None:
    """The fixed about lines use the plan's titles."""
    assert ABOUT_TITLE == "Looked up how I worked it out"
    assert ABOUT_BODY == "Used my notes from the earlier answer. No new queries were needed."
