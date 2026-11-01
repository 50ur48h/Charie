"""The writer end to end: filled 09 blocks with exact copies (P10.10).

FakeAi stands in for understanding, the enough check and the writer;
the notebook is seeded by hand so the cited label is deterministic.
"""

import asyncio

import pytest

from charie.chat.analyst import enough as enough_module
from charie.chat.analyst import review as review_module
from charie.chat.analyst import write as write_module
from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.notebook import Notebook, NumberValue, by_label, check
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Message
from tests.integration.chat import test_data_helper as shop
from tests.integration.chat.conftest import _understanding_reply, fake_understanding


@pytest.fixture()
def writer_shop(db_session, shop_db, test_db_url, monkeypatch):
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


def _seeded_number(db_session, ctx):
    book = Notebook.load(db_session, ctx.message_id, ctx.chat_id)
    return book.add_number(
        "Net sales",
        NumberValue(value="359.00", unit="money"),
        proof={"sql": "SELECT 1"},
    )


def _ready(monkeypatch) -> None:
    """No tasks to run; the writer has labelled blocks to fill."""
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
                            },
                            {
                                "kind": "fact",
                                "text": "That [n1] covers the month.",
                                "proof": ["n1"],
                                "starts_paragraph": False,
                            },
                        ],
                    },
                    {
                        "type": "kpis",
                        "kpis": [{"title": "Net sales", "value": "n1"}],
                    },
                ]
            }
        ],
    )


def test_check_resolves_only_current_cards(db_session, writer_shop) -> None:
    """A missing label is nothing; a replaced label stays unusable."""
    ctx = shop._ctx(db_session, writer_shop)
    _seeded_number(db_session, ctx)
    book = Notebook.load(db_session, ctx.message_id, ctx.chat_id)
    book.add_number("Orders", NumberValue(value="5", unit="count"), proof={})
    book.replace("n1", "n2", "A better query.")
    assert by_label(db_session, ctx.message_id, ctx.chat_id, "n9") is None
    assert check(db_session, ctx.message_id, ctx.chat_id, "n1") is None
    assert check(db_session, ctx.message_id, ctx.chat_id, "n2") is not None


def test_writer_blocks_show_exact_copies(db_session, writer_shop, monkeypatch) -> None:
    """The saved answer carries the figure in text and kpis, never the label."""
    ctx = shop._ctx(db_session, writer_shop)
    _seeded_number(db_session, ctx)
    _ready(monkeypatch)
    asyncio.run(answer_question(ctx))
    saved = db_session.get(Message, ctx.message_id)
    assert saved.status == "done"
    assert saved.answer["kb_version"] == 1
    reading, text, kpis, note, method = saved.answer["blocks"]
    assert reading == {
        "type": "reading",
        "text": "I read this as **net sales** for 1–31 Dec 2025.",
    }
    assert text["type"] == "text"
    assert [line["text"] for line in text["paragraphs"][0]["sentences"]] == [
        "Net sales were $359.00.",
        "That $359.00 covers the month.",
    ]
    assert kpis == {
        "type": "kpis",
        "items": [{"label": "Net sales", "value": "$359.00"}],
    }
    assert note["type"] == "callout"
    assert method["type"] == "method"
    assert "Round 1 done: no new tasks, so no new answers." in method["steps"]
    assert "The rounds answered the question." in method["steps"]
    assert "[n" not in str(saved.answer["blocks"])
