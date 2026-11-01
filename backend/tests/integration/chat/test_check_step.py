"""The review and check lines on a passing answer (P10.12 Task 6).

The writer's draft renders, the reviewer approves, and the checks pass:
the thinking panel shows the review line and the new check wording.
"""

import asyncio

import pytest
from sqlalchemy import select

from charie.chat.analyst import enough as enough_module
from charie.chat.analyst import review as review_module
from charie.chat.analyst import write as write_module
from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.notebook import Notebook, NumberValue
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Message, ThinkingEvent
from tests.integration.chat import test_data_helper as shop
from tests.integration.chat.conftest import _understanding_reply, fake_understanding


@pytest.fixture()
def check_shop(db_session, shop_db, test_db_url, monkeypatch):
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


def test_check_line_lists_failures(db_session, check_shop, monkeypatch) -> None:
    """A good draft leaves a review line and the passing check line."""
    ctx = shop._ctx(db_session, check_shop)
    book = Notebook.load(db_session, ctx.message_id, ctx.chat_id)
    book.add_number("Net sales", NumberValue(value="359.00", unit="money"), proof={})
    fake_understanding(monkeypatch, _understanding_reply(asks=[]))
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
                                "text": "Net sales were [n1].",
                                "proof": ["n1"],
                                "starts_paragraph": True,
                            }
                        ],
                    }
                ]
            }
        ],
    )
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    assert saved.answer["blocks"][1]["paragraphs"][0]["sentences"][0]["text"] == (
        "Net sales were $359.00."
    )
    lines = db_session.scalars(
        select(ThinkingEvent)
        .where(ThinkingEvent.message_id == ctx.message_id)
        .order_by(ThinkingEvent.seq)
    ).all()
    review, check = lines[-2], lines[-1]
    assert (review.title, review.status) == ("Review: looks good", "done")
    assert (check.title, check.status) == ("Checks passed", "done")
