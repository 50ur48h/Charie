"""Step 3 profiles every column, from a sample when big (P07.7)."""

import pytest
from sqlalchemy import func, select, text

from charie.learner.steps import profile
from charie.learner.steps.base import SkipItem, StepContext
from charie.learner.steps.structure import run_job as run_structure
from charie.shared.connectors.base import ConnectorError
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.chat import QueryRun
from charie.shared.tables.learning import LearningRun


@pytest.fixture()
def profile_ctx(db_session, shop_db):
    """The shop scanned, ready to profile; strict mode is per-test."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="profile", version_id=version_id)
    db_session.add(run)
    db_session.commit()
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    def make_ctx(strict: bool = False) -> StepContext:
        return StepContext(
            session=db_session,
            run_id=run.id,
            version_id=version_id,
            source=shop_db["source"],
            connector=shop_db["connector"],
            strict_mode=strict,
            settings={},
            say=say,
        )

    run_structure(
        JobInfo(id=1, kind="scan_structure", payload={"step": "structure"}, run_id=run.id),
        make_ctx(),
    )
    return make_ctx(), said


def _run(ctx, table: str) -> None:
    profile.run_job(
        JobInfo(id=2, kind="profile_table", payload={"table": table}, run_id=ctx.run_id),
        ctx,
    )


def _profile_of(db_session, version_id: int, key: str) -> dict:
    entry = store.get_entry(db_session, version_id, key)
    assert entry is not None
    return (entry.details or {}).get("profile") or {}


def test_every_column_gets_a_profile(profile_ctx, db_session) -> None:
    ctx, said = profile_ctx
    jobs = profile.make_jobs(ctx)
    assert {job["table"] for job in jobs} == {
        "shop.stores",
        "shop.cities",
        "shop.orders",
        "shop.order_lines",
        "shop.order_notes",
        "shop.coupons",
        "shop.daily_sales",
    }
    for job in jobs:
        _run(ctx, job["table"])
    orders = store.get_entry(db_session, ctx.version_id, "table.shop.orders")
    assert orders is not None
    assert orders.details["profiled_at"] is not None
    assert orders.details["sampled"] is False
    assert orders.details["rows_profiled"] == 10
    total = _profile_of(db_session, ctx.version_id, "column.shop.orders.total")
    assert total["rows_seen"] == 10
    assert total["empty"] == 0 and total["empty_share"] == 0.0
    assert total["distinct"] == 10
    assert total["min"] == 28.25 and total["max"] == 63.0
    created = _profile_of(db_session, ctx.version_id, "column.shop.orders.created_at")
    assert created["min"] is None
    assert created["date_from"] == "2025-01-05" and created["date_to"] == "2025-03-28"
    expires = _profile_of(db_session, ctx.version_id, "column.shop.coupons.expires_on")
    assert expires["date_from"] is None and expires["date_to"] is None
    view = store.get_entry(db_session, ctx.version_id, "table.shop.daily_sales")
    assert view is not None and view.details["rows_profiled"] == 10
    assert ("info", "Looked at orders: 6 columns, all 10 rows.") in said


def test_empty_and_distinct_counts(profile_ctx, db_session) -> None:
    ctx, _ = profile_ctx
    _run(ctx, "shop.orders")
    _run(ctx, "shop.stores")
    status = _profile_of(db_session, ctx.version_id, "column.shop.orders.status")
    assert status["distinct"] == 1 and status["empty"] == 0
    city = _profile_of(db_session, ctx.version_id, "column.shop.stores.city_id")
    assert city["distinct"] == 3


def test_top_values_and_text_min_max(profile_ctx, db_session) -> None:
    ctx, _ = profile_ctx
    _run(ctx, "shop.orders")
    _run(ctx, "shop.stores")
    status = _profile_of(db_session, ctx.version_id, "column.shop.orders.status")
    assert status["top_values"] == [{"value": "delivered", "count": 10}]
    assert status["min"] == "delivered" and status["max"] == "delivered"
    assert status["min_length"] == 9 and status["max_length"] == 9
    names = _profile_of(db_session, ctx.version_id, "column.shop.stores.name")
    assert names["top_values"] == [
        {"value": "Downtown", "count": 1},
        {"value": "Hilltop", "count": 1},
        {"value": "Riverside", "count": 1},
    ]


def test_patterns_are_found(profile_ctx, db_session, shop_db) -> None:
    ctx, said = profile_ctx
    with shop_db["owner"].begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE shop.codelist (code text);"
                " GRANT SELECT ON shop.codelist TO charie_shop_test"
            )
        )
        conn.execute(
            text(
                "INSERT INTO shop.codelist (code) VALUES ('ABCD12'), ('EFGH34'),"
                " ('IJKL56'), ('MNOP78'), ('QRST90'), ('UVWX12'), ('YZAB34'),"
                " ('CDEF56'), ('GHIJ78'), ('xyz')"
            )
        )
    run_structure(
        JobInfo(id=3, kind="scan_structure", payload={"step": "structure"}, run_id=ctx.run_id),
        ctx,
    )
    for job in profile.make_jobs(ctx):
        _run(ctx, job["table"])
    code = _profile_of(db_session, ctx.version_id, "column.shop.codelist.code")
    assert code["pattern"] == "AAAA99" and code["pattern_share"] == 0.9
    assert (
        "found",
        "codelist.code looks like a code: AAAA99 (90% of values).",
    ) in said
    # The real coupon codes share no 80% shape, so the plan's example holds none.
    coupon = _profile_of(db_session, ctx.version_id, "column.shop.orders.coupon_code")
    assert coupon["pattern"] is None


def test_big_table_is_sampled(profile_ctx, db_session, monkeypatch) -> None:
    ctx, said = profile_ctx
    monkeypatch.setattr(profile, "SAMPLE_ABOVE_ROWS", 5)
    _run(ctx, "shop.orders")
    orders = store.get_entry(db_session, ctx.version_id, "table.shop.orders")
    assert orders is not None and orders.details["sampled"] is True
    assert orders.details["rows_profiled"] == 10
    total = _profile_of(db_session, ctx.version_id, "column.shop.orders.total")
    assert total["sampled"] == 10
    assert ("info", "Looked at orders: 6 columns, a sample of 200K rows.") in said


def test_strict_mode_keeps_no_values(profile_ctx, db_session) -> None:
    ctx, said = profile_ctx
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
    _run(strict, "shop.orders")
    for key in ("column.shop.orders.status", "column.shop.orders.total"):
        found = _profile_of(db_session, ctx.version_id, key)
        assert found["top_values"] == [] and found["strict"] is True
    status = _profile_of(db_session, ctx.version_id, "column.shop.orders.status")
    assert status["min"] is None and status["max"] is None
    assert status["min_length"] == 9 and status["max_length"] == 9
    total = _profile_of(db_session, ctx.version_id, "column.shop.orders.total")
    assert total["min"] == 28.25
    created = _profile_of(db_session, ctx.version_id, "column.shop.orders.created_at")
    assert created["date_from"] == "2025-01-05"
    names = store.list_entries(db_session, ctx.version_id, kinds=["name"])
    assert names == []


def test_forbidden_table_is_skipped(profile_ctx, db_session) -> None:
    ctx, said = profile_ctx
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
    jobs = profile.make_jobs(ctx)
    assert "shop.coupons" not in {job["table"] for job in jobs}
    for job in jobs:
        _run(ctx, job["table"])
    coupons = store.get_entry(db_session, ctx.version_id, "table.shop.coupons")
    assert coupons is not None and coupons.details.get("profiled_at") is None
    assert (
        "info",
        "Skipping shop.coupons: your notes say never to use it.",
    ) in said


def test_always_empty_column_gets_a_line(profile_ctx, db_session, shop_db) -> None:
    ctx, said = profile_ctx
    with shop_db["owner"].begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE shop.scraps (id integer, note text);"
                " GRANT SELECT ON shop.scraps TO charie_shop_test"
            )
        )
        conn.execute(text("INSERT INTO shop.scraps (id, note) VALUES (1, NULL), (2, NULL)"))
    run_structure(
        JobInfo(id=3, kind="scan_structure", payload={"step": "structure"}, run_id=ctx.run_id),
        ctx,
    )
    _run(ctx, "shop.scraps")
    note = _profile_of(db_session, ctx.version_id, "column.shop.scraps.note")
    assert note["empty"] == 2 and note["empty_share"] == 1.0
    assert ("found", "scraps.note is always empty.") in said


def test_finish_counts_profiled(profile_ctx) -> None:
    ctx, said = profile_ctx
    for job in profile.make_jobs(ctx):
        _run(ctx, job["table"])
    profile.finish_step(ctx)
    assert said[-1] == ("found", "7 tables and views, 24 columns")


def test_slow_table_is_skipped(profile_ctx, db_session) -> None:
    ctx, _ = profile_ctx

    class SlowConnector:
        def run_query(self, sql):
            raise ConnectorError("query_timeout", "The query took too long.")

    slow = StepContext(
        session=ctx.session,
        run_id=ctx.run_id,
        version_id=ctx.version_id,
        source=ctx.source,
        connector=SlowConnector(),
        strict_mode=False,
        settings={},
        say=ctx.say,
    )
    with pytest.raises(SkipItem, match="took too long to look at"):
        _run(slow, "shop.orders")
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(QueryRun)
            .where(QueryRun.learning_run_id == ctx.run_id, QueryRun.status == "timeout")
        )
        == 1
    )
    orders = store.get_entry(db_session, ctx.version_id, "table.shop.orders")
    assert orders is not None and orders.details.get("profiled_at") is None
