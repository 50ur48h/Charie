"""Only the checked answer reaches the stream, with real totals (P10.13).

FakeAi stands in for understanding, enough, planning, the writer and
the reviewer. The cost, query and document rows are seeded by hand so
the saved totals have known values.
"""

import asyncio
import json
import re
import time

import pytest
from sqlalchemy import func, select

from charie.chat.analyst import enough as enough_module
from charie.chat.analyst import plan as plan_module
from charie.chat.analyst import review as review_module
from charie.chat.analyst import write as write_module
from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.notebook import Notebook, NumberValue, QuoteValue
from charie.chat.analyst.stream import FEEDS, MessageFeed, block_text, stream_answer, text_deltas
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Message, QueryRun, ThinkingEvent
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.usage import AiCall
from tests.conftest import log_in
from tests.integration.chat import test_data_helper as shop
from tests.integration.chat.conftest import _understanding_reply, fake_understanding

RAW_LABEL = re.compile(r"\[(?:n|t|q|p)\d+\]")


@pytest.fixture()
def loop_shop(db_session, shop_db, test_db_url):
    """The seeded version, as the data helper tests see it."""
    return shop._seeded_version(db_session)


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


def _good_draft():
    return {
        "blocks": [
            {
                "type": "text",
                "sentences": [
                    {
                        "kind": "fact",
                        "text": "Net sales were [n1].",
                        "proof": ["n1"],
                        "starts_paragraph": True,
                    }
                ],
            }
        ]
    }


def _good_review():
    return {"verdict": "good", "fixes": [], "needs_more_data": False, "missing_data": ""}


def _ready(monkeypatch, writes, reviews, enough=1, plans=0) -> None:
    fake_understanding(monkeypatch, _understanding_reply(asks=[]))
    _patch(monkeypatch, enough_module, "check_enough", [{"enough": True, "missing": ""}] * enough)
    _patch(monkeypatch, plan_module, "plan_round", [{"tasks": []}] * plans)
    _patch(monkeypatch, write_module, "write_answer", writes)
    _patch(monkeypatch, review_module, "review_answer", reviews)


def _seeded(ctx, db_session):
    book = Notebook.load(db_session, ctx.message_id, ctx.chat_id)
    book.add_number("Net sales", NumberValue(value="359.00", unit="money"), proof={})
    return ctx


def _long_sentence() -> str:
    return (
        "Net sales were strong across every restaurant this December, "
        "with dinner service leading lunch by a wide margin every week."
    )


def test_text_deltas_word_boundaries() -> None:
    """Chunks break on whitespace and join back exactly."""
    text = _long_sentence() + " " + _long_sentence()
    chunks = text_deltas(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 120 or " " not in chunk
    for first, second in zip(chunks, chunks[1:], strict=False):
        assert first[-1].isspace() or second[0].isspace(), (first[-65:], second[:65])
    assert "".join(chunks) == text
    assert text_deltas("") == []


def test_checked_only() -> None:
    """The stream carries the checked blocks, never a raw label."""
    message_id = 4242
    feed = MessageFeed()
    FEEDS[message_id] = feed
    try:
        blocks = [
            {"type": "reading", "text": "I read this as net sales for December."},
            {
                "type": "text",
                "paragraphs": [
                    {"sentences": [{"kind": "fact", "text": _long_sentence()}]},
                    {"sentences": [{"kind": "fact", "text": "Net sales were $359.00."}]},
                ],
            },
            {
                "type": "table",
                "title": "Checked numbers",
                "columns": [{"key": "what", "label": "What"}],
                "rows": [{"what": "Net sales"}],
            },
        ]
        summary = {"seconds": 4, "steps": 9, "queries": 1, "documents": 0}
        stream_answer(message_id, blocks, summary)
        kinds = [item.event for item in feed.events]
        assert kinds[0] == "summary"
        assert feed.events[0].data == summary
        assert kinds[1:3] == ["block", "block"]
        assert feed.events[1].data["index"] == 0
        assert feed.events[2].data == {
            "index": 1,
            "block": {"type": "text", "paragraphs": []},
        }
        deltas = [item.data["delta"] for item in feed.events if item.event == "text"]
        assert len(deltas) > 1
        assert "".join(deltas) == block_text(blocks[1])
        for item in feed.events:
            assert not RAW_LABEL.search(json.dumps(item.data)), item
    finally:
        FEEDS.pop(message_id, None)


def test_save_before_done(db_session, loop_shop, monkeypatch) -> None:
    """Reload and streamed completion show the same answer and totals."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    FEEDS[ctx.message_id] = MessageFeed()
    try:
        _ready(monkeypatch, [_good_draft()], [_good_review()])
        asyncio.run(answer_question(ctx))
    finally:
        feed = FEEDS.pop(ctx.message_id, None)
    assert feed is not None
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    assert saved.answer["kb_version"] == ctx.kb_version_id
    assert saved.answer["data_through"] == (
        ctx.data_through.isoformat() if ctx.data_through is not None else None
    )
    assert isinstance(saved.seconds, int) and saved.seconds >= 0
    assert saved.steps == db_session.scalar(
        select(func.count(ThinkingEvent.id)).where(ThinkingEvent.message_id == ctx.message_id)
    )
    assert saved.queries == 0
    assert saved.documents == 0
    assert saved.cost_usd == 0.0
    kinds = [item.event for item in feed.events]
    assert kinds[-1] == "done"
    summary = next(item for item in feed.events if item.event == "summary")
    assert summary.data == {
        "seconds": saved.seconds,
        "steps": saved.steps,
        "queries": saved.queries,
        "documents": saved.documents,
    }
    assert feed.events[-1].data["cost_usd"] == saved.cost_usd == 0.0
    streamed = "".join(item.data["delta"] for item in feed.events if item.event == "text")
    assert streamed == block_text(saved.answer["blocks"][1])


def test_real_cost_counts(db_session, loop_shop, monkeypatch) -> None:
    """Seeded calls, queries and quotes land in the saved totals."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    book = Notebook.load(db_session, ctx.message_id, ctx.chat_id)
    for document_id in (7, 7, 12):
        book.add_quote(
            "Freshness note",
            QuoteValue(
                text="fresh daily",
                document_id=document_id,
                document="notes/inbox",
                section_id=2,
                heading_path="",
                location="page 2",
            ),
        )
    for purpose in ("net sales", "orders"):
        db_session.add(
            QueryRun(message_id=ctx.message_id, purpose=purpose, sql_text="SELECT 1", status="ok")
        )
    db_session.add(
        AiCall(
            app="chat",
            job="write_answer",
            provider="meta",
            model="test",
            cost_usd=0.0011,
            message_id=ctx.message_id,
            status="ok",
        )
    )
    db_session.add(
        AiCall(
            app="chat",
            job="write_answer",
            provider="meta",
            model="test",
            cost_usd=0.0002,
            message_id=ctx.message_id,
            status="failed",
        )
    )
    db_session.commit()
    FEEDS[ctx.message_id] = MessageFeed()
    try:
        _ready(monkeypatch, [_good_draft()], [_good_review()])
        asyncio.run(answer_question(ctx))
    finally:
        feed = FEEDS.pop(ctx.message_id, None)
    assert feed is not None
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    assert saved.queries == 2
    assert saved.documents == 2
    assert float(saved.cost_usd) == pytest.approx(0.0013)
    summary = next(item for item in feed.events if item.event == "summary")
    assert summary.data["queries"] == 2
    assert summary.data["documents"] == 2
    assert feed.events[-1].data["cost_usd"] == pytest.approx(0.0013)


def test_finish_now_delivers_fallback(db_session, loop_shop, monkeypatch) -> None:
    """Finish now still delivers the checked numbers, marked stopped."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    fake_understanding(monkeypatch, _understanding_reply(asks=[]))
    FEEDS[ctx.message_id] = MessageFeed()
    try:
        ctx.state.finish_requested.set()
        asyncio.run(answer_question(ctx))
    finally:
        feed = FEEDS.pop(ctx.message_id, None)
    assert feed is not None
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "stopped"
    assert saved.finished_at is not None
    warns = [
        block
        for block in saved.answer["blocks"]
        if block["type"] == "callout" and block.get("tone") == "warn"
    ]
    assert any("checked numbers" in warn["text"] for warn in warns)
    tables = [
        block
        for block in saved.answer["blocks"]
        if block["type"] == "table" and block.get("title") == "Checked numbers"
    ]
    assert tables
    assert {"what": "Net sales", "value": {"v": 359.0, "f": "$359.00"}} in tables[0]["rows"]
    assert feed.events[-1].event == "done"
    assert feed.events[-1].data["status"] == "stopped"
    titles = [
        line.title
        for line in db_session.scalars(
            select(ThinkingEvent)
            .where(ThinkingEvent.message_id == ctx.message_id)
            .order_by(ThinkingEvent.seq)
        ).all()
    ]
    assert "Stopped early. Showing the checked numbers gathered so far." in titles


def test_finish_now_empty_notebook_stays_plain(db_session, loop_shop, monkeypatch) -> None:
    """Nothing checked means a plain stop with no answer."""
    ctx = shop._ctx(db_session, loop_shop)
    fake_understanding(monkeypatch, _understanding_reply(asks=[]))
    ctx.state.finish_requested.set()
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "stopped"
    assert saved.answer is None


def _parse_sse(text: str) -> list[dict]:
    """Blank-line separated events into {id, event, data} dicts."""
    events = []
    for chunk in text.replace("\r\n", "\n").split("\n\n"):
        item: dict = {}
        for line in chunk.splitlines():
            if line.startswith("id:"):
                item["id"] = line[3:].strip()
            elif line.startswith("event:"):
                item["event"] = line[6:].strip()
            elif line.startswith("data:"):
                item["data"] = json.loads(line[5:].strip())
        if item:
            events.append(item)
    return events


def _wait_done(client, chat_id: int, timeout_s: float = 30.0) -> None:
    """Poll the chat until the assistant message finishes."""
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        opened = client.get(f"/api/chats/{chat_id}").json()
        if opened["messages"][1]["status"] == "done":
            return
        time.sleep(0.05)
    raise AssertionError("the answer never finished")


def test_restart_high_cursor(chat_client, db_session, monkeypatch) -> None:
    """A stale cursor never suppresses the rebuilt completion."""
    fake_understanding(monkeypatch)
    log_in(chat_client)
    db_session.add(KbVersion(number=1, status="published", made_by="first_learning"))
    db_session.commit()
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    assistant_id = chat_client.post(
        f"/api/chats/{chat_id}/messages", json={"text": "Net sales?"}
    ).json()["assistant_message_id"]
    _wait_done(chat_client, chat_id)
    FEEDS.pop(assistant_id, None)
    events = _parse_sse(
        chat_client.get(
            f"/api/messages/{assistant_id}/stream", headers={"Last-Event-ID": "999"}
        ).text
    )
    assert events[0]["event"] == "reset"
    assert events[0]["id"] == "0"
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["status"] == "done"
    assert any(event["event"] == "summary" for event in events)


def test_reconnect_mid_text() -> None:
    """A dropped connection resumes inside the text with no repeat."""
    message_id = 4343
    feed = MessageFeed()
    FEEDS[message_id] = feed
    try:
        blocks = [
            {
                "type": "text",
                "paragraphs": [
                    {"sentences": [{"kind": "fact", "text": _long_sentence()}]},
                    {"sentences": [{"kind": "fact", "text": _long_sentence()}]},
                ],
            }
        ]
        stream_answer(message_id, blocks, {"seconds": 1, "steps": 2, "queries": 0, "documents": 0})

        async def _first_three():
            seen = []
            gen = feed.follow(0)
            try:
                for _ in range(3):
                    seen.append(await gen.__anext__())
            finally:
                await gen.aclose()
            return seen

        first = asyncio.run(_first_three())
        assert [item.event for item in first] == ["summary", "block", "text"]
        rest = feed.events_after(first[-1].id)
        assert rest
        assert [item.id for item in rest] == list(range(first[-1].id + 1, feed.events[-1].id + 1))
        full = "".join(item.data["delta"] for item in feed.events if item.event == "text")
        assert (
            "".join(item.data["delta"] for item in first if item.event == "text")
            + "".join(item.data["delta"] for item in rest if item.event == "text")
            == full
            == block_text(blocks[0])
        )
    finally:
        FEEDS.pop(message_id, None)
