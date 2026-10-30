"""Step 5 explains each table; code keeps what checks out (P07.9, fake AI)."""

import pytest

from charie.learner.steps import explain_tables
from charie.learner.steps.base import StepContext
from charie.learner.steps.links import run_job as run_links
from charie.learner.steps.profile import run_job as run_profile
from charie.learner.steps.structure import run_job as run_structure
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.learning import LearningRun


def _orders_reply() -> dict:
    return {
        "table_meaning": "An order is what a customer buys.",
        "grain": "one order",
        "columns": [
            {"name": "id", "meaning": "The order's own number.", "unit": "id"},
            {
                "name": "store_id",
                "meaning": "Which store sold it.",
                "unit": "id",
                "refers_to": "stores",
            },
            {"name": "created_at", "meaning": "When the order was placed.", "unit": "date"},
            {"name": "status", "meaning": "How the order ended.", "unit": "text"},
            {
                "name": "total",
                "meaning": "What the customer paid.",
                "unit": "money",
                "unit_name": "dollars",
                "currency": "USD",
            },
            {
                "name": "coupon_code",
                "meaning": "The coupon the customer used.",
                "unit": "code",
                "refers_to": "coupons",
            },
        ],
        "name_list": {"id_column": "", "name_column": ""},
    }


def _stores_reply() -> dict:
    return {
        "table_meaning": "A store is a shop that sells.",
        "grain": "one store",
        "columns": [
            {"name": "id", "meaning": "The store's own number.", "unit": "id"},
            {"name": "name", "meaning": "What the store is called.", "unit": "text"},
            {"name": "city", "meaning": "The city the store is in.", "unit": "text"},
            {"name": "city_id", "meaning": "The city's number.", "unit": "id"},
        ],
        "name_list": {"id_column": "id", "name_column": "name"},
    }


@pytest.fixture()
def explain_ctx(db_session, shop_db, monkeypatch):
    """Shop scanned, profiled and linked; the fake AI answers explain_table."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="explain_tables", version_id=version_id)
    db_session.add(run)
    db_session.commit()
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    ctx = StepContext(
        session=db_session,
        run_id=run.id,
        version_id=version_id,
        source=shop_db["source"],
        connector=shop_db["connector"],
        strict_mode=False,
        settings={},
        say=say,
    )
    run_structure(
        JobInfo(id=1, kind="scan_structure", payload={"step": "structure"}, run_id=run.id),
        ctx,
    )

    for table in ["shop.stores", "shop.cities", "shop.orders"]:
        run_profile(
            JobInfo(id=2, kind="profile_table", payload={"table": table}, run_id=run.id),
            ctx,
        )
    from charie.learner.steps import links as links_step

    for job in links_step.make_jobs(ctx):
        run_links(
            JobInfo(id=3, kind="test_link", payload={"step": "links", **job}, run_id=run.id),
            ctx,
        )
    return ctx, said, monkeypatch


def _run(ctx, monkeypatch, reply: dict, table: str) -> FakeAi:
    fake = FakeAi().reply("explain_table", reply)
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(explain_tables, "get_ai", lambda: client)
    explain_tables.run_job(
        JobInfo(id=4, kind="explain_table", payload={"table": table}, run_id=ctx.run_id),
        ctx,
    )
    return fake


def test_entries_get_meanings_and_confidence(explain_ctx, db_session) -> None:
    ctx, said, monkeypatch = explain_ctx
    _run(ctx, monkeypatch, _orders_reply(), "shop.orders")
    entry = store.get_entry(db_session, ctx.version_id, "table.shop.orders")
    assert entry is not None
    assert entry.meaning == "An order is what a customer buys."
    assert entry.confidence == "checked"
    assert entry.details["grain"] == "one order"
    assert entry.details["explained"] is True
    total = store.get_entry(db_session, ctx.version_id, "column.shop.orders.total")
    assert total is not None and total.meaning == "What the customer paid."
    assert total.confidence == "checked"
    assert total.details["unit"] == "money" and total.details["currency"] == "USD"
    assert total.details["checks_failed"] == []
    assert (
        "found",
        "Explained orders: one row is one order. All 6 columns check out against the data.",
    ) in said


def test_name_list_for_a_small_table(explain_ctx, db_session) -> None:
    ctx, said, monkeypatch = explain_ctx
    _run(ctx, monkeypatch, _stores_reply(), "shop.stores")
    entry = store.get_entry(db_session, ctx.version_id, "name.shop.stores")
    assert entry is not None
    assert entry.title == "Names in stores"
    assert entry.confidence == "checked"
    assert entry.details["items"] == [
        {"id": 1, "name": "Downtown"},
        {"id": 3, "name": "Hilltop"},
        {"id": 2, "name": "Riverside"},
    ]
    assert entry.details["truncated"] is False


def test_missing_columns_keep_their_entries(explain_ctx, db_session) -> None:
    ctx, said, monkeypatch = explain_ctx
    reply = _orders_reply()
    reply["columns"] = [column for column in reply["columns"] if column["name"] != "status"]
    _run(ctx, monkeypatch, reply, "shop.orders")
    status = store.get_entry(db_session, ctx.version_id, "column.shop.orders.status")
    assert status is not None and status.details.get("explained") is not True
    assert ("warning", "I couldn't explain 1 column of orders: status.") in said


def test_strict_mode_sends_no_values_and_keeps_no_names(explain_ctx, db_session) -> None:
    ctx, said, monkeypatch = explain_ctx
    strict = StepContext(
        session=ctx.session,
        run_id=ctx.run_id,
        version_id=ctx.version_id,
        source=ctx.source,
        connector=ctx.connector,
        strict_mode=True,
        settings={},
        say=ctx.say,
    )
    table = store.get_entry(db_session, ctx.version_id, "table.shop.stores").details or {}
    strict_input = explain_tables.build_explain_input(db_session, ctx.version_id, table, True)[
        "table"
    ]
    assert all(column["top_values"] == [] for column in strict_input["columns"])
    _run(strict, monkeypatch, _stores_reply(), "shop.stores")
    names = store.list_entries(db_session, ctx.version_id, kinds=["name"])
    assert names == []
    assert (
        "info",
        "Strict mode is on, so I didn't keep the names in stores.",
    ) in said


def test_forbidden_table_is_not_explained(explain_ctx, db_session) -> None:
    ctx, said, monkeypatch = explain_ctx
    store.upsert_entry(
        db_session,
        ctx.version_id,
        "rule.never_use_table.forbid_coupons",
        "rule",
        "Leave out the coupons table",
        "The coupons table is never used.",
        {"rule_type": "never_use_table", "table": "shop.coupons"},
        "confirmed",
        [{"type": "owner_notes", "quote": "Never use the coupons table."}],
        "Sorted from your notes",
    )
    db_session.commit()
    jobs = explain_tables.make_jobs(ctx)
    assert "shop.coupons" not in {job["table"] for job in jobs}
    for job in jobs:
        if job["table"] not in ("shop.orders", "shop.stores"):
            continue
        _run(
            ctx,
            monkeypatch,
            _orders_reply() if "orders" in job["table"] else _stores_reply(),
            job["table"],
        )
    coupons = store.get_entry(db_session, ctx.version_id, "table.shop.coupons")
    assert coupons is not None and coupons.details.get("explained") is not True
    assert (
        "info",
        "Skipping shop.coupons: the owner's notes say never to use it.",
    ) in said


def test_confirmed_meaning_is_kept(explain_ctx, db_session) -> None:
    ctx, said, monkeypatch = explain_ctx
    total = store.get_entry(db_session, ctx.version_id, "column.shop.orders.total")
    assert total is not None
    store.upsert_entry(
        db_session,
        ctx.version_id,
        total.key,
        "column",
        total.title,
        "The shop's own charge for the order.",
        total.details or {},
        "confirmed",
        total.sources or [],
        "Edited by you",
    )
    db_session.commit()
    _run(ctx, monkeypatch, _orders_reply(), "shop.orders")
    kept = store.get_entry(db_session, ctx.version_id, "column.shop.orders.total")
    assert kept is not None
    assert kept.meaning == "The shop's own charge for the order."
    assert kept.confidence == "confirmed"
