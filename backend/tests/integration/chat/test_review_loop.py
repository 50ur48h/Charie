"""The review loop: fix twice, one more round, or the fallback (P10.12).

FakeAi stands in for understanding, enough, planning, the writer and the
reviewer; the notebook is seeded by hand so the cited label is fixed.
"""

import asyncio
import time

import pytest
from sqlalchemy import select

from charie.chat.analyst import answer as answer_module
from charie.chat.analyst import enough as enough_module
from charie.chat.analyst import plan as plan_module
from charie.chat.analyst import review as review_module
from charie.chat.analyst import write as write_module
from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.notebook import Notebook, NumberValue, QuoteValue
from charie.chat.analyst.stream import FEEDS, MessageFeed
from charie.chat.analyst.write import AnswerDraft
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Message, ThinkingEvent
from tests.integration.chat import test_data_helper as shop
from tests.integration.chat.conftest import _understanding_reply, fake_understanding


@pytest.fixture()
def loop_shop(db_session, shop_db, test_db_url, monkeypatch):
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


def _seeded(ctx, db_session):
    book = Notebook.load(db_session, ctx.message_id, ctx.chat_id)
    book.add_number("Net sales", NumberValue(value="359.00", unit="money"), proof={})
    return ctx


def _ready(monkeypatch, writes, reviews, enough=1, plans=0) -> dict:
    fake_understanding(monkeypatch, _understanding_reply(asks=[]))
    _patch(monkeypatch, enough_module, "check_enough", [{"enough": True, "missing": ""}] * enough)
    _patch(monkeypatch, plan_module, "plan_round", [{"tasks": []}] * plans)
    return {
        "write": _patch(monkeypatch, write_module, "write_answer", writes),
        "review": _patch(monkeypatch, review_module, "review_answer", reviews),
    }


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


def _bad_draft():
    draft = _good_draft()
    draft["blocks"][0]["sentences"][0]["proof"] = []
    return draft


def _good_review():
    return {"verdict": "good", "fixes": [], "needs_more_data": False, "missing_data": ""}


def _lines(db_session, message_id):
    return db_session.scalars(
        select(ThinkingEvent)
        .where(ThinkingEvent.message_id == message_id)
        .order_by(ThinkingEvent.seq)
    ).all()


def test_fallback_shows_checked_numbers(db_session, loop_shop, monkeypatch) -> None:
    """Two failing drafts show the checked numbers, all marked shown."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    bad = [_bad_draft(), _bad_draft(), _bad_draft()]
    _ready(monkeypatch, bad, [_good_review(), _good_review(), _good_review()])
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    kinds = [block["type"] for block in saved.answer["blocks"]]
    assert kinds == ["reading", "callout", "table", "callout", "method"]
    warn = saved.answer["blocks"][1]
    assert warn["text"].startswith("I couldn't write a fully checked explanation")
    checked = saved.answer["blocks"][2]
    assert checked["title"] == "Checked numbers"
    assert {"what": "Net sales", "value": {"v": 359.0, "f": "$359.00"}} in checked["rows"]
    titles = [line.title for line in _lines(db_session, ctx.message_id)]
    assert (
        "I couldn't write a fully checked explanation, so I'm showing the checked numbers."
        in titles
    )
    db_session.expire_all()
    book = Notebook.load(db_session, ctx.message_id, ctx.chat_id)
    assert book.get("n1").proof.get("shown") is True


def test_failure_goes_back_to_writer(db_session, loop_shop, monkeypatch) -> None:
    """A fix that passes shows the answer with the fix line behind it."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    _ready(monkeypatch, [_bad_draft(), _good_draft()], [_good_review(), _good_review()])
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.answer["blocks"][1]["paragraphs"][0]["sentences"][0]["text"] == (
        "Net sales were $359.00."
    )
    titles = [line.title for line in _lines(db_session, ctx.message_id)]
    assert "Fixing the answer (try 1 of 2)" in titles
    assert titles[-1] == "Checks passed"


def test_needs_more_data_runs_one_more_round(db_session, loop_shop, monkeypatch) -> None:
    """The reviewer can ask for one more guided round."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    _ready(
        monkeypatch,
        [_good_draft(), _good_draft()],
        [
            {
                "verdict": "fix",
                "fixes": [],
                "needs_more_data": True,
                "missing_data": "sales by restaurant",
            },
            _good_review(),
        ],
        enough=2,
        plans=1,
    )
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    titles = [line.title for line in _lines(db_session, ctx.message_id)]
    assert any(title.startswith("Round 2") for title in titles)
    assert "Fixing the answer (try 1 of 2)" in titles


def test_needs_more_data_without_time_rewrites(db_session, loop_shop, monkeypatch) -> None:
    """No time left means rewrite with the reviewer's fixes, not another round."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    ctx.settings["thinking_minutes"] = 0
    fix = {"problem": "Name the month.", "how_to_fix": "Cite [p1] in the first sentence."}
    _ready(
        monkeypatch,
        [_good_draft(), _good_draft()],
        [
            {"verdict": "fix", "fixes": [fix], "needs_more_data": True, "missing_data": "x"},
            _good_review(),
        ],
    )
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    titles = [line.title for line in _lines(db_session, ctx.message_id)]
    assert "Fixing the answer (try 1 of 2)" in titles
    assert not any(title.startswith("Round 2") for title in titles)


def test_reviewer_fix_goes_back_to_writer(db_session, loop_shop, monkeypatch) -> None:
    """Two review fixes show by name, then the passing review."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    fixes = [
        {"problem": "Name the month.", "how_to_fix": "Cite [p1]."},
        {"problem": "Round the figure.", "how_to_fix": "Keep [n1] short."},
    ]
    fakes = _ready(
        monkeypatch,
        [_good_draft(), _good_draft()],
        [
            {"verdict": "fix", "fixes": fixes, "needs_more_data": False, "missing_data": ""},
            _good_review(),
        ],
    )
    asyncio.run(answer_question(ctx))
    lines = _lines(db_session, ctx.message_id)
    first = next(line for line in lines if line.title.startswith("Review:"))
    assert (first.title, first.status) == ("Review: 2 things to fix", "failed")
    assert "Name the month." in first.body
    assert lines[-1].title == "Checks passed"
    second_write = str(fakes["write"].calls[1])
    assert "Name the month." in second_write


def test_review_input_has_filled_numbers(db_session, loop_shop, monkeypatch) -> None:
    """The reviewer reads the answer with real numbers, not labels."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    fakes = _ready(monkeypatch, [_good_draft()], [_good_review()])
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    assert "$359.00" in str(fakes["review"].calls[0])


def test_two_fixes_then_fallback(db_session, loop_shop, monkeypatch) -> None:
    """An unhappy reviewer twice means the fallback, not a third rewrite."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    fix = {
        "verdict": "fix",
        "fixes": [{"problem": "Be clearer.", "how_to_fix": "Rewrite."}],
        "needs_more_data": False,
        "missing_data": "",
    }
    bad = [_bad_draft(), _bad_draft(), _bad_draft()]
    _ready(monkeypatch, bad, [fix, fix, fix])
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    assert saved.answer["blocks"][1]["type"] == "callout"
    titles = [line.title for line in _lines(db_session, ctx.message_id)]
    assert titles.count("Review: 1 thing to fix") == 3
    assert "Fixing the answer (try 2 of 2)" in titles


def test_reviewer_unhappy_but_checks_pass_shows_answer(db_session, loop_shop, monkeypatch) -> None:
    """One unhappy review with passing checks still ends in the answer."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    fix = {
        "verdict": "fix",
        "fixes": [{"problem": "Be warmer.", "how_to_fix": "Soften the note."}],
        "needs_more_data": False,
        "missing_data": "",
    }
    _ready(monkeypatch, [_good_draft(), _good_draft()], [fix, _good_review()])
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    assert saved.answer["blocks"][1]["paragraphs"][0]["sentences"][0]["text"] == (
        "Net sales were $359.00."
    )
    titles = [line.title for line in _lines(db_session, ctx.message_id)]
    assert "Review: 1 thing to fix" in titles


def test_finish_during_writing_delivers_stopped_fallback(
    db_session, loop_shop, monkeypatch
) -> None:
    """Finish set mid-write stops the loop with the checked fallback."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    _ready(monkeypatch, [_good_draft()], [_good_review()])

    def slow_write(ctx, fixes=None):
        time.sleep(0.5)
        return AnswerDraft.model_validate(_good_draft())

    monkeypatch.setattr(answer_module, "write_answer", slow_write)
    FEEDS[ctx.message_id] = MessageFeed()
    try:

        async def _run():
            task = asyncio.create_task(answer_question(ctx))
            await asyncio.sleep(0.1)
            ctx.state.finish_requested.set()
            await task

        asyncio.run(_run())
    finally:
        feed = FEEDS.pop(ctx.message_id, None)
    assert feed is not None
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "stopped"
    warns = [block for block in saved.answer["blocks"] if block["type"] == "callout"]
    assert any("checked numbers" in warn["text"] for warn in warns)
    assert feed.events[-1].event == "done"
    assert feed.events[-1].data["status"] == "stopped"


def test_no_rewrite_after_finish(db_session, loop_shop, monkeypatch) -> None:
    """One failed draft plus Finish means no second write call."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    _ready(monkeypatch, [_bad_draft(), _bad_draft(), _bad_draft()], [_good_review()] * 3)
    calls: list = []
    real_write = answer_module.write_answer

    def counting_write(ctx, fixes=None):
        calls.append(1)
        if len(calls) == 1:
            ctx.state.finish_requested.set()
        return real_write(ctx, fixes=fixes)

    monkeypatch.setattr(answer_module, "write_answer", counting_write)
    asyncio.run(answer_question(ctx))
    assert len(calls) == 1
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "stopped"
    warns = [block for block in saved.answer["blocks"] if block["type"] == "callout"]
    assert any("checked numbers" in warn["text"] for warn in warns)


def test_loop_stays_responsive_during_write(db_session, loop_shop, monkeypatch) -> None:
    """Other work runs while the writer thinks; the loop never blocks."""
    ctx = _seeded(shop._ctx(db_session, loop_shop), db_session)
    _ready(monkeypatch, [_good_draft()], [_good_review()])
    order: list = []

    def slow_write(ctx, fixes=None):
        time.sleep(0.5)
        order.append("write")
        return AnswerDraft.model_validate(_good_draft())

    monkeypatch.setattr(answer_module, "write_answer", slow_write)

    async def _marker():
        await asyncio.sleep(0.1)
        order.append("marker")

    async def _run():
        await asyncio.gather(answer_question(ctx), _marker())

    asyncio.run(_run())
    assert order == ["marker", "write"]


def test_stray_digits_left_out_of_check_body(db_session, loop_shop, monkeypatch) -> None:
    """A digit-carrying passage stays in the details, never in the body."""
    ctx = shop._ctx(db_session, loop_shop)
    book = Notebook.load(db_session, ctx.message_id, ctx.chat_id)
    book.add_number("Orders", NumberValue(value="30", unit="count"), proof={})
    book.add_quote(
        "Freshness note",
        QuoteValue(
            text="fresh daily",
            document_id=1,
            document="notes/inbox",
            section_id=2,
            heading_path="",
            location="page 2",
        ),
    )
    draft = {
        "blocks": [
            {
                "type": "text",
                "sentences": [
                    {
                        "kind": "note",
                        "text": 'We sold [n1] and it was "fresh daily 30 orders total now".',
                        "proof": ["n1"],
                        "starts_paragraph": True,
                    }
                ],
            }
        ]
    }
    _ready(monkeypatch, [draft, draft, draft], [_good_review(), _good_review(), _good_review()])
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.answer["blocks"][1]["type"] == "callout"
    lines = _lines(db_session, ctx.message_id)
    checks = [line for line in lines if line.title.startswith("Checks found")]
    assert checks
    assert "30" not in checks[-1].body
    assert any(
        "30 orders total now" in failure["message"] for failure in checks[-1].details["failures"]
    )
