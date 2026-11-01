"""charie_answer: the harness's in-process answer function (P10.14).

FakeAi stands in for every AI job, so these tests never touch the network
and need no key values. The shop database answers the SQL for real.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from charie.chat.analyst import enough as enough_module
from charie.chat.analyst import plan as plan_module
from charie.chat.analyst import review as review_module
from charie.chat.analyst import understand as understand_module
from charie.chat.analyst import write as write_module
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import DbCostLog, MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.knowledge import sql_writer
from charie.shared.settings import set_setting
from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.usage import AiCall
from tests.integration.chat import test_data_helper as shop
from tests.integration.chat.conftest import _understanding_reply
from tests.integration.chat.test_data_helper import data_module
from tests.questions.charie_answer import NotReadyError, _summarize, charie_answer
from tests.questions.format import Question

DEC_A = (
    "SELECT COUNT(*) AS value FROM shop.orders"
    " WHERE created_on >= DATE '2025-12-01' AND created_on < DATE '2026-01-01'"
)
DEC_B = (
    "SELECT COUNT(DISTINCT id) AS value FROM shop.orders"
    " WHERE created_on >= DATE '2025-12-01' AND created_on < DATE '2026-01-01'"
)

NEW_KIND_REPLY = _understanding_reply(
    kind="new_kind",
    reading="I read this as new orders for [p1].",
    periods=[{"kind": "month", "number": 12}],
    asks=[{"new_metric": "How many shop orders are there?"}],
)


def _patch(monkeypatch, module, job, replies, log=None):
    """Point one module at queued FakeAi replies (no network, ever)."""
    fake = FakeAi()
    for reply in replies:
        fake.reply(job, reply)
    monkeypatch.setattr(
        module,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=log or MemoryCostLog(), sleep=lambda s: None),
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
                        "text": "Shop orders were [n1].",
                        "proof": ["n1"],
                        "starts_paragraph": True,
                    }
                ],
            }
        ]
    }


def _good_review():
    return {"verdict": "good", "fixes": [], "needs_more_data": False, "missing_data": ""}


def _shop(monkeypatch, db_session, test_db_url):
    """The seeded shop version, answering SQL on the test database."""
    set_setting(db_session, "time_zone", "America/Chicago")
    db_session.commit()
    version_id = shop._seeded_version(db_session)
    monkeypatch.setattr(
        data_module,
        "customer_connector",
        lambda session: PostgresConnector.from_url(test_db_url),
    )
    return version_id


def _standard_fakes(monkeypatch, understanding=None, log=None, tasks=True):
    """Every AI job the answer flow can reach."""
    _patch(
        monkeypatch,
        understand_module,
        "understand_question",
        [understanding or _understanding_reply()],
        log,
    )
    _patch(monkeypatch, enough_module, "check_enough", [{"enough": True}], log)
    _patch(
        monkeypatch,
        write_module,
        "write_answer",
        [_good_draft(), _good_draft(), _good_draft()],
        log,
    )
    _patch(
        monkeypatch,
        review_module,
        "review_answer",
        [_good_review(), _good_review(), _good_review()],
        log,
    )
    if tasks:
        _patch(
            monkeypatch,
            sql_writer,
            "write_sql",
            [
                {"sql": DEC_A, "notes": "Count every row."},
                {"sql": DEC_B, "notes": "Count each order once."},
            ],
            log,
        )


def _clear_question(**overrides):
    args = {
        "id": "t-clear",
        "kind": "clear",
        "question": "How many shop orders were there in December?",
        "checked_by": "Step 0 test",
    }
    args.update(overrides)
    return Question(**args)


def test_not_ready_without_published_version(db_session) -> None:
    """No learned version: the harness stops before spending anything."""
    with pytest.raises(NotReadyError):
        charie_answer(_clear_question(), private=False)


def test_no_key_input(db_session, shop_db, test_db_url, monkeypatch) -> None:
    """A clear question answers with fakes only: no key, no tracked spend."""
    for key in ("META_API_KEY", "AZURE_OPENAI_API_KEY", "AI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    _shop(monkeypatch, db_session, test_db_url)
    _standard_fakes(monkeypatch, NEW_KIND_REPLY)

    answer = charie_answer(_clear_question(kind="new_kind"), private=False)

    assert answer.status == "ok"
    assert answer.chat_url.startswith("/chat/")
    assert answer.text != ""
    rows = db_session.scalars(select(AiCall)).all()
    assert rows == []
    assert answer.cost_usd == Decimal("0")
    assert answer.earlier_turns_cost_usd == Decimal("0")


def test_shown_ok_numbers(db_session, shop_db, test_db_url, monkeypatch) -> None:
    """Only the shown number is reported: a second agreed number stays out."""
    _shop(monkeypatch, db_session, test_db_url)
    _standard_fakes(
        monkeypatch,
        _understanding_reply(
            kind="new_kind",
            reading="I read this as new orders for [p1].",
            periods=[{"kind": "month", "number": 12}],
            asks=[
                {"new_metric": "How many shop orders are there?"},
                {"new_metric": "How many shop orders are there?"},
            ],
        ),
    )
    fake_sql = FakeAi()
    for _ in range(2):
        fake_sql.reply("write_sql", {"sql": DEC_A, "notes": "Count every row."})
        fake_sql.reply("write_sql", {"sql": DEC_B, "notes": "Count each order once."})
    monkeypatch.setattr(
        sql_writer,
        "get_ai",
        lambda: AiClient(provider=fake_sql, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )

    answer = charie_answer(_clear_question(kind="new_kind"), private=False)

    assert answer.status == "ok"
    assert [(shown.label, shown.value, shown.unit) for shown in answer.numbers] == [
        ("n1", Decimal("6"), "count")
    ]


def test_cannot_tell_needs_choice(db_session, shop_db) -> None:
    """A needs_choice ending maps to asked_choice, with the reading as text."""
    version_id = shop._seeded_version(db_session)
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    message = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="needs_choice",
        mode="thinking",
        kb_version_id=version_id,
        answer={
            "blocks": [{"type": "reading", "text": "Which one?"}],
            "options": [{"label": "A", "value": "a"}],
        },
        started_at=datetime.now(UTC),
    )
    db_session.add(message)
    db_session.commit()

    answer = _summarize(db_session, chat.id, message.id, datetime.now(UTC), False)

    assert answer.status == "ok"
    assert answer.asked_choice is True
    assert answer.text == "Which one?"
    assert answer.numbers == []


def test_cost_separation(db_session, shop_db, test_db_url, monkeypatch) -> None:
    """Two turns split the tracked spend: the last turn and everything before."""
    _shop(monkeypatch, db_session, test_db_url)
    log = DbCostLog()
    _patch(
        monkeypatch,
        understand_module,
        "understand_question",
        [NEW_KIND_REPLY, NEW_KIND_REPLY],
        log,
    )
    _patch(monkeypatch, enough_module, "check_enough", [{"enough": True}, {"enough": True}], log)
    _patch(monkeypatch, plan_module, "plan_round", [{"tasks": []}, {"tasks": []}], log)
    _patch(
        monkeypatch,
        write_module,
        "write_answer",
        [_good_draft()] * 6,
        log,
    )
    _patch(
        monkeypatch,
        review_module,
        "review_answer",
        [_good_review()] * 6,
        log,
    )
    fake_sql = FakeAi()
    for _ in range(2):
        fake_sql.reply("write_sql", {"sql": DEC_A, "notes": "Count every row."})
        fake_sql.reply("write_sql", {"sql": DEC_B, "notes": "Count each order once."})
    monkeypatch.setattr(
        sql_writer,
        "get_ai",
        lambda: AiClient(provider=fake_sql, cost_log=log, sleep=lambda s: None),
    )

    answer = charie_answer(
        _clear_question(
            kind="new_kind",
            chat=["How many shop orders were there in December?"],
            question="And what were net sales?",
        ),
        private=False,
    )

    assert answer.status == "ok"
    assert answer.cost_usd > Decimal("0")
    assert answer.earlier_turns_cost_usd > Decimal("0")
    rows = db_session.scalars(select(AiCall).where(AiCall.app == "tests")).all()
    total = sum((Decimal(str(row.cost_usd)) for row in rows), Decimal("0"))
    assert total == answer.cost_usd + answer.earlier_turns_cost_usd
