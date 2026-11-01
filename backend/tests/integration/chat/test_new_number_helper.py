"""The new-number helper on the shop database (P10.7).

FakeAi stands in for both ways; the canned SQL runs for real through
the safety checker on the shop database.
"""

import pytest
from sqlalchemy import select

from charie.chat.analyst.helpers import data as data_module
from charie.chat.analyst.helpers.new_number import run_new_number_task
from charie.chat.analyst.helpers.tasks import Task
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.knowledge import sql_writer
from charie.shared.knowledge.sql_writer import results_agree
from charie.shared.settings import set_setting
from charie.shared.tables.chat import QueryRun
from charie.shared.tables.questions import LearnerTodo
from tests.integration.chat import test_data_helper as shop

DEC_A = (
    "SELECT COUNT(*) AS value FROM shop.orders"
    " WHERE created_on >= DATE '2025-12-01' AND created_on < DATE '2026-01-01'"
)
DEC_B = (
    "SELECT COUNT(DISTINCT id) AS value FROM shop.orders"
    " WHERE created_on >= DATE '2025-12-01' AND created_on < DATE '2026-01-01'"
)
DEC_NONE = (
    "SELECT COUNT(*) AS value FROM shop.orders"
    " WHERE created_on >= DATE '2026-01-01' AND created_on < DATE '2026-02-01'"
)


@pytest.fixture()
def shop_new_number(db_session, shop_db, test_db_url, monkeypatch):
    """The seeded tiny shop, as the data helper tests see it."""
    set_setting(db_session, "time_zone", "America/Chicago")
    db_session.commit()
    version_id = shop._seeded_version(db_session)
    monkeypatch.setattr(
        data_module,
        "customer_connector",
        lambda session: PostgresConnector.from_url(test_db_url),
    )
    return version_id


def _ctx(db_session, version_id):
    return shop._ctx(db_session, version_id, question="How many shop orders are there?")


def _new_task() -> Task:
    return Task(
        kind="new_number",
        why="Work out a new number two ways for the period.",
        new_metric="How many shop orders are there?",
        periods=["p2"],
    )


def _client(monkeypatch, replies) -> FakeAi:
    fake = FakeAi()
    for sql, notes in replies:
        fake.reply("write_sql", {"sql": sql, "notes": notes})
    monkeypatch.setattr(
        sql_writer,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    return fake


def test_agree_adds_items_and_todo(db_session, shop_new_number, monkeypatch) -> None:
    """Both ways count 6 December orders: one number, one to-do, two runs."""
    _client(
        monkeypatch,
        [(DEC_A, "Count every row."), (DEC_B, "Count each order once.")],
    )
    ctx = _ctx(db_session, shop_new_number)
    run_new_number_task(_new_task(), ctx)
    book = shop._notebook(db_session, ctx)
    numbers = shop._numbers(book)
    assert len(numbers) == 1
    assert numbers[0].value["value"] == "6"
    assert numbers[0].value["unit"] == "count"
    assert numbers[0].proof["way"] == "A+B"
    assert numbers[0].proof["fact_key"]["metric"] == "new:how many shop orders are there"
    assert "(not a standard measure yet)" in numbers[0].description
    todos = db_session.scalars(select(LearnerTodo).where(LearnerTodo.status == "open")).all()
    assert len(todos) == 1
    assert todos[0].kind == "new_metric"
    assert "COUNT(*) AS value" in todos[0].details["sql_a"]
    assert "COUNT(DISTINCT id) AS value" in todos[0].details["sql_b"]
    runs = db_session.scalars(select(QueryRun)).all()
    assert [(run.way, run.status) for run in runs] == [("A", "ok"), ("B", "ok")]
    query = [line for line in shop._lines(db_session, ctx.message_id) if line.kind == "query"]
    assert len(query) == 1
    assert query[0].status == "done"
    assert query[0].body == "Way A: Count every row. Way B: Count each order once."


def test_disagree_adds_no_numbers(db_session, shop_new_number, monkeypatch) -> None:
    """Way B finds nothing: a disagreement finding and a decision, no numbers."""
    _client(
        monkeypatch,
        [(DEC_A, "Count every row."), (DEC_NONE, "Count future rows.")],
    )
    ctx = _ctx(db_session, shop_new_number)
    run_new_number_task(_new_task(), ctx)
    book = shop._notebook(db_session, ctx)
    assert shop._numbers(book) == []
    findings = [item for item in book.items() if item.kind == "finding"]
    assert len(findings) == 1
    assert findings[0].value["type"] == "disagreement"
    assert findings[0].value["text"] == (
        "Way A and way B disagree for How many shop orders are there: A gave 6, B gave 0."
    )
    decisions = [
        line for line in shop._lines(db_session, ctx.message_id) if line.kind == "decision"
    ]
    assert len(decisions) == 1
    todos = db_session.scalars(select(LearnerTodo).where(LearnerTodo.status == "open")).all()
    assert todos == []


def test_blocked_marks_couldnt_check(db_session, shop_new_number, monkeypatch) -> None:
    """An unsafe way blocks the task: a couldnt_check finding, no numbers."""
    _client(monkeypatch, [("SELECT * FROM shop.secrets", "")])
    ctx = _ctx(db_session, shop_new_number)
    run_new_number_task(_new_task(), ctx)
    book = shop._notebook(db_session, ctx)
    assert shop._numbers(book) == []
    findings = [item for item in book.items() if item.kind == "finding"]
    assert len(findings) == 1
    assert findings[0].value["type"] == "couldnt_check"
    assert findings[0].value["text"] == (
        "Couldn't check How many shop orders are there: the queries weren't safe to run."
    )
    failed = [
        line
        for line in shop._lines(db_session, ctx.message_id)
        if line.kind == "query" and line.status == "failed"
    ]
    assert len(failed) == 1
    assert failed[0].body == findings[0].value["text"]


def test_one_open_todo_per_description(db_session, shop_new_number, monkeypatch) -> None:
    """A second agreeing run adds numbers but no second to-do."""
    _client(
        monkeypatch,
        [
            (DEC_A, "Count every row."),
            (DEC_B, "Count each order once."),
            (DEC_A, "Count every row."),
            (DEC_B, "Count each order once."),
        ],
    )
    ctx = _ctx(db_session, shop_new_number)
    run_new_number_task(_new_task(), ctx)
    run_new_number_task(_new_task(), ctx)
    book = shop._notebook(db_session, ctx)
    assert len(shop._numbers(book)) == 2
    todos = db_session.scalars(select(LearnerTodo).where(LearnerTodo.status == "open")).all()
    assert len(todos) == 1


def test_agreement_uses_the_self_test_rule() -> None:
    """0.4% apart agrees; 0.6% apart does not (the self-test rule)."""
    assert results_agree([[1000]], [[1004]]) is True
    assert results_agree([[1000]], [[1006]]) is False
    assert results_agree([["north", 100]], [["north", 100]]) is True
    assert results_agree([["north", 5]], [["south", 5]]) is False
    assert results_agree([["north", 1]], []) is False
    assert results_agree([["north", 0]], [["north", 0]]) is False
