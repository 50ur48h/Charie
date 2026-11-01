"""Rounds of starter and planned tasks on the shop database (P10.9).

FakeAi stands in for understanding, the planner and the enough check;
the data tasks run for real on the shop database.
"""

import asyncio

import pytest

from charie.chat.analyst import enough as enough_module
from charie.chat.analyst import plan as plan_module
from charie.chat.analyst.helpers import data as data_module
from charie.chat.analyst.loop import run_rounds
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.settings import set_setting
from tests.integration.chat import test_data_helper as shop
from tests.integration.chat.conftest import _understanding_reply, fake_understanding


@pytest.fixture()
def shop_rounds(db_session, shop_db, test_db_url, monkeypatch):
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
    return shop._ctx(db_session, version_id, question="How did orders do in December?")


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


def _understand(monkeypatch, asks) -> None:
    fake_understanding(
        monkeypatch,
        _understanding_reply(
            kind="clear",
            reading="I read this as orders for [p1].",
            periods=[{"kind": "month", "number": 12}],
            asks=asks,
        ),
    )


def _lines(db_session, ctx, kind: str):
    return [
        line
        for line in shop._lines(db_session, ctx.message_id)
        if line.kind == kind and line.status == "done"
    ]


def _rounds(db_session, ctx):
    return [line for line in _lines(db_session, ctx, "step") if line.title.startswith("Round")]


def test_rounds_run_until_enough(db_session, shop_rounds, monkeypatch) -> None:
    """Round 1 runs the starters; round 2 runs the planned split; then done."""
    _understand(monkeypatch, [{"metric_key": "orders"}])
    plan = _patch(
        monkeypatch,
        plan_module,
        "plan_round",
        [
            {
                "tasks": [
                    {
                        "kind": "recipe",
                        "metric_key": "orders",
                        "split_by": ["dimension.status"],
                        "why": "Get orders by status.",
                    }
                ]
            },
        ],
    )
    check = _patch(
        monkeypatch,
        enough_module,
        "check_enough",
        [
            {"enough": False, "missing": "the split by status"},
            {"enough": True, "missing": ""},
        ],
    )
    ctx = _ctx(db_session, shop_rounds)
    ran = asyncio.run(run_rounds(ctx))
    assert len(ran) == 2
    assert len(plan.calls) == 1
    assert len(check.calls) == 2
    book = shop._notebook(db_session, ctx)
    assert sorted({item.round for item in book.items()}) == [0, 1, 2]
    assert [line.title for line in _rounds(db_session, ctx)] == [
        "Round 1 done: still needs the split by status.",
        "Round 2 done: the question is answered.",
    ]
    assert [line.body for line in _lines(db_session, ctx, "check")] == [
        "the split by status",
        "Nothing missing.",
    ]


def test_empty_round_still_checks(db_session, shop_rounds, monkeypatch) -> None:
    """A round with no new tasks still runs the enough check."""
    _understand(monkeypatch, [{"metric_key": "orders"}])
    _patch(monkeypatch, plan_module, "plan_round", [{"tasks": []}])
    check = _patch(
        monkeypatch,
        enough_module,
        "check_enough",
        [
            {"enough": False, "missing": "the split by status"},
            {"enough": True, "missing": ""},
        ],
    )
    ctx = _ctx(db_session, shop_rounds)
    ran = asyncio.run(run_rounds(ctx))
    assert len(ran) == 1
    assert len(check.calls) == 2
    assert [line.title for line in _rounds(db_session, ctx)] == [
        "Round 1 done: still needs the split by status.",
        "Round 2 done: no new tasks, so no new answers.",
    ]
