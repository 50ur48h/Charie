"""Private analyst runs through the real adapter (P10.14).

A private run saves nothing shared: no learner to-dos, no memories, and no
visible chat. A crashed private run leaves no chat row behind, either.
"""

from decimal import Decimal

from sqlalchemy import select

from charie.chat import chat_store
from charie.chat.analyst import enough as enough_module
from charie.chat.analyst import review as review_module
from charie.chat.analyst import understand as understand_module
from charie.chat.analyst import write as write_module
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import DbCostLog, MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.errors import ApiError
from charie.shared.knowledge import sql_writer
from charie.shared.settings import set_setting
from charie.shared.tables.chat import Chat, Memory
from charie.shared.tables.questions import LearnerTodo
from tests.integration.chat import test_data_helper as shop
from tests.integration.chat.conftest import _understanding_reply
from tests.integration.chat.test_data_helper import data_module
from tests.questions.charie_answer import charie_answer
from tests.questions.format import Question

DEC_A = (
    "SELECT COUNT(*) AS value FROM shop.orders"
    " WHERE created_on >= DATE '2025-12-01' AND created_on < DATE '2026-01-01'"
)
DEC_B = (
    "SELECT COUNT(DISTINCT id) AS value FROM shop.orders"
    " WHERE created_on >= DATE '2025-12-01' AND created_on < DATE '2026-01-01'"
)


def _patch(monkeypatch, module, job, replies, log=None):
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


def _question():
    return Question(
        id="t-private",
        kind="new_kind",
        question="How many shop orders were there in December?",
        checked_by="Step 0 test",
    )


def _fakes(monkeypatch, db_session, test_db_url, turns=1):
    """The seeded shop plus fakes for every job one agreeing round reaches."""
    set_setting(db_session, "time_zone", "America/Chicago")
    db_session.commit()
    shop._seeded_version(db_session)
    monkeypatch.setattr(
        data_module,
        "customer_connector",
        lambda session: PostgresConnector.from_url(test_db_url),
    )
    _patch(
        monkeypatch,
        understand_module,
        "understand_question",
        [
            _understanding_reply(
                kind="new_kind",
                reading="I read this as new orders for [p1].",
                periods=[{"kind": "month", "number": 12}],
                asks=[{"new_metric": "How many shop orders are there?"}],
            )
        ]
        * turns,
    )
    _patch(monkeypatch, enough_module, "check_enough", [{"enough": True}] * turns)
    _patch(monkeypatch, write_module, "write_answer", [_good_draft()] * (3 * turns))
    _patch(monkeypatch, review_module, "review_answer", [_good_review()] * (3 * turns))
    fake_sql = FakeAi()
    for _ in range(turns):
        fake_sql.reply("write_sql", {"sql": DEC_A, "notes": "Count every row."})
        fake_sql.reply("write_sql", {"sql": DEC_B, "notes": "Count each order once."})
    monkeypatch.setattr(
        sql_writer,
        "get_ai",
        lambda: AiClient(provider=fake_sql, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )


def _todos(db_session):
    return db_session.scalars(select(LearnerTodo).where(LearnerTodo.status == "open")).all()


def test_no_shared_side_effects(db_session, shop_db, test_db_url, monkeypatch) -> None:
    """Private first: no to-do. Public next: the same run offers one to-do."""
    _fakes(monkeypatch, db_session, test_db_url, turns=2)

    hidden = charie_answer(_question(), private=True)

    assert hidden.status == "ok"
    assert hidden.chat_url == ""
    assert _todos(db_session) == []
    assert db_session.scalars(select(Memory)).all() == []
    assert chat_store.list_chats(db_session) == []
    kept = db_session.scalars(select(Chat)).all()
    assert len(kept) == 1 and kept[0].private is True

    shown = charie_answer(_question(), private=False)

    assert shown.status == "ok"
    assert shown.chat_url.startswith("/chat/")
    assert len(_todos(db_session)) == 1
    visible = chat_store.list_chats(db_session)
    assert [chat.id for chat in visible] == [int(shown.chat_url.rsplit("/", 1)[1])]


def test_cleanup_on_error(db_session, shop_db, test_db_url, monkeypatch) -> None:
    """A crashed private run reports the error and leaves no chat behind."""
    _fakes(monkeypatch, db_session, test_db_url)
    # A raw provider failure escapes the helpers' enumerated catches, so the
    # run crashes the way a dead driver would (an AiError would fall back).
    broken = FakeAi()
    broken.fail("write_sql", RuntimeError("The driver died mid-query."))
    monkeypatch.setattr(
        sql_writer,
        "get_ai",
        lambda: AiClient(provider=broken, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )

    answer = charie_answer(_question(), private=True)

    assert answer.status == "error"
    assert answer.chat_url == ""
    assert db_session.scalars(select(Chat)).all() == []
    assert _todos(db_session) == []
    assert db_session.scalars(select(Memory)).all() == []
    try:
        chat_store.get_chat(db_session, 1)
        missing = False
    except ApiError:
        missing = True
    assert missing


def test_failure_keeps_costs(db_session, shop_db, test_db_url, monkeypatch) -> None:
    """A crashed private run reports its real spend before the chat is dropped."""
    monkeypatch.setenv("AI_REPLAY", "replay")
    set_setting(db_session, "time_zone", "America/Chicago")
    db_session.commit()
    shop._seeded_version(db_session)
    monkeypatch.setattr(
        data_module,
        "customer_connector",
        lambda session: PostgresConnector.from_url(test_db_url),
    )
    log = DbCostLog()
    _patch(
        monkeypatch,
        understand_module,
        "understand_question",
        [
            _understanding_reply(
                kind="new_kind",
                reading="I read this as new orders for [p1].",
                periods=[{"kind": "month", "number": 12}],
                asks=[{"new_metric": "How many shop orders are there?"}],
            )
        ],
        log,
    )
    broken = FakeAi()
    broken.fail("write_sql", RuntimeError("The driver died mid-query."))
    monkeypatch.setattr(
        sql_writer,
        "get_ai",
        lambda: AiClient(provider=broken, cost_log=log, sleep=lambda s: None),
    )

    answer = charie_answer(_question(), private=True)

    assert answer.status == "error"
    # The understand call ran before the crash: real spend, failed turn.
    assert answer.cost_usd > Decimal("0")
    assert answer.earlier_turns_cost_usd == Decimal("0")
    assert db_session.scalars(select(Chat)).all() == []
