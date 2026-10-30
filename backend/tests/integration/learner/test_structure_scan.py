"""Step 2 scans a small shop database: objects, entries, dates (P07.6)."""

from datetime import date

import pytest
from sqlalchemy import func, select, text

from charie.learner.steps.base import StepContext
from charie.learner.steps.structure import (
    STRUCTURE_STEP,
    finish_step,
    make_jobs,
    run_job,
)
from charie.shared.connectors.base import ConnectorError, QueryResult
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.chat import QueryRun
from charie.shared.tables.knowledge import KbChange
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.sources import DataSource


@pytest.fixture()
def step_ctx(db_session, shop_db):
    """A step context on the throwaway database with the shop connected."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="structure", version_id=version_id)
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
    return ctx, said


def _run(ctx) -> None:
    run_job(
        JobInfo(
            id=1,
            kind="scan_structure",
            payload={"step": "structure"},
            run_id=ctx.run_id,
            attempts=1,
        ),
        ctx,
    )


def test_no_connector_makes_no_jobs(step_ctx, db_session) -> None:
    ctx, _ = step_ctx
    empty = StepContext(
        session=db_session,
        run_id=ctx.run_id,
        version_id=ctx.version_id,
        source=None,
        connector=None,
        strict_mode=False,
        settings={},
        say=lambda kind, message, details=None: None,
    )
    assert make_jobs(empty) == []
    assert STRUCTURE_STEP.empty_note == "There's no database connected yet, so I skipped this step."


def test_scan_finds_tables_views_and_columns(step_ctx, db_session) -> None:
    ctx, said = step_ctx
    assert make_jobs(ctx) == [{}]
    _run(ctx)
    tables = store.list_entries(db_session, ctx.version_id, kinds=["table"])
    assert len(tables) == 7
    assert sum(1 for entry in tables if entry.details["is_view"]) == 1
    orders = store.get_entry(db_session, ctx.version_id, "table.shop.orders")
    assert orders is not None and orders.confidence == "guessed"
    assert orders.details["comment"] == "One row per customer order."
    assert orders.details["row_estimate"] == 10
    assert orders.details["primary_key"] == ["id"]
    assert orders.details["foreign_keys"] == [
        {"columns": ["store_id"], "ref_table": "shop.stores", "ref_columns": ["id"]}
    ]
    assert orders.details["columns"] == [
        "id",
        "store_id",
        "created_at",
        "status",
        "total",
        "coupon_code",
    ]
    total = store.get_entry(db_session, ctx.version_id, "column.shop.orders.total")
    assert total is not None and total.details["data_type"] == "numeric(10,2)"
    assert total.details["nullable"] is True
    columns = store.list_entries(db_session, ctx.version_id, kinds=["column"])
    assert len(columns) == 24
    assert ("found", "Found 6 tables and 1 view, with 24 columns.") in said
    purposes = {
        row.purpose
        for row in db_session.scalars(
            select(QueryRun).where(QueryRun.learning_run_id == ctx.run_id)
        )
    }
    assert {
        "Read the list of tables",
        "Read the columns of every table",
        "Read the primary, unique and foreign keys",
    } <= purposes
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(QueryRun)
            .where(QueryRun.learning_run_id == ctx.run_id, QueryRun.status != "ok")
        )
        == 0
    )


def test_scan_makes_guessed_entries(step_ctx, db_session) -> None:
    ctx, _ = step_ctx
    _run(ctx)
    orders = store.get_entry(db_session, ctx.version_id, "table.shop.orders")
    assert orders is not None
    assert orders.title == "orders"
    assert orders.meaning == (
        "A table with 10 rows and 6 columns. Charie explains it in a later step."
    )
    assert [source["type"] for source in orders.sources] == ["structure"]
    assert orders.sources[0]["text"] == "Read from the database structure"
    view = store.get_entry(db_session, ctx.version_id, "table.shop.daily_sales")
    assert view is not None and view.title == "daily_sales"
    assert view.meaning.startswith("A view (a saved query) with ")
    city = store.get_entry(db_session, ctx.version_id, "column.shop.stores.city_id")
    assert city is not None and city.title == "stores.city_id"
    assert city.meaning == "An integer column in stores. Charie explains it in a later step."
    for entry in store.list_entries(db_session, ctx.version_id):
        assert entry.confidence in ("guessed", "checked")


def test_data_range_ignores_future_dates(step_ctx, db_session) -> None:
    ctx, said = step_ctx
    _run(ctx)
    span = store.get_entry(db_session, ctx.version_id, "data_range.shop.orders")
    assert span is not None and span.confidence == "checked"
    assert span.title == "Dates in orders"
    assert span.meaning == (
        "The data in orders goes from 5 Jan 2025 to 28 Mar 2025 (column created_at)."
    )
    assert span.details["date_column"] == "created_at"
    assert span.details["date_from"] == "2025-01-05"
    assert span.details["date_to"] == "2025-03-28"
    assert span.details["exact"] is True
    assert span.sources[0]["type"] == "query"
    assert "min(" in span.sources[0]["sql"]
    assert store.get_entry(db_session, ctx.version_id, "data_range.shop.coupons") is None
    assert ("found", "The newest data is from 28 Mar 2025.") in said


def test_data_through_and_source_counts(step_ctx, db_session) -> None:
    ctx, _ = step_ctx
    _run(ctx)
    source = shop_db_source(db_session, ctx)
    assert source.data_through is not None
    assert source.data_through.date().isoformat() == "2025-03-28"
    assert source.checked_at is not None
    assert source.details["table_count"] == 6
    assert source.details["view_count"] == 1
    assert source.details["column_count"] == 24
    assert source.details["total_rows"] == 52


def shop_db_source(db_session, ctx):
    """The source row, reloaded after the scan saved it."""
    return db_session.get(DataSource, ctx.source.id)


def test_second_scan_changes_nothing(step_ctx, db_session) -> None:
    ctx, _ = step_ctx
    _run(ctx)
    changes = _change_count(db_session, ctx)
    _run(ctx)
    assert _change_count(db_session, ctx) == changes


def _change_count(db_session, ctx) -> int:
    return db_session.scalar(
        select(func.count()).select_from(KbChange).where(KbChange.version_id == ctx.version_id)
    )


def test_missing_table_loses_its_entries(step_ctx, db_session, shop_db) -> None:
    ctx, _ = step_ctx
    _run(ctx)
    assert store.get_entry(db_session, ctx.version_id, "table.shop.order_notes") is not None
    with shop_db["owner"].begin() as conn:
        conn.execute(text("DROP TABLE shop.order_notes"))
    _run(ctx)
    assert store.get_entry(db_session, ctx.version_id, "table.shop.order_notes") is None
    assert store.get_entry(db_session, ctx.version_id, "column.shop.order_notes.note") is None
    assert store.get_entry(db_session, ctx.version_id, "table.shop.orders") is not None
    removed = db_session.scalars(
        select(KbChange).where(KbChange.version_id == ctx.version_id, KbChange.change == "removed")
    ).all()
    assert {row.key for row in removed} >= {
        "table.shop.order_notes",
        "column.shop.order_notes.order_id",
        "column.shop.order_notes.note",
    }
    assert all(row.reason == "No longer in the database" for row in removed)


def test_forbidden_table_is_listed_with_a_line(step_ctx, db_session) -> None:
    ctx, said = step_ctx
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
    _run(ctx)
    coupons = store.get_entry(db_session, ctx.version_id, "table.shop.coupons")
    assert coupons is not None
    assert store.get_entry(db_session, ctx.version_id, "column.shop.coupons.code") is not None
    assert store.get_entry(db_session, ctx.version_id, "data_range.shop.coupons") is None
    assert (
        "info",
        "Your notes say never to use shop.coupons. I'll list it, but I won't study it.",
    ) in said


def test_finish_counts_the_scan(step_ctx, db_session) -> None:
    ctx, said = step_ctx
    _run(ctx)
    finish_step(ctx)
    assert said[-1] == ("found", "6 tables, 1 view and 24 columns")


def test_slow_table_uses_sample_and_null_rows(step_ctx, db_session, monkeypatch) -> None:
    ctx, said = step_ctx
    real = ctx.connector.run_query

    def slow(query, *args, **kwargs):
        if "TABLESAMPLE" in query and '"orders"' in query:
            return QueryResult(
                columns=["n", "n_0", "min_0", "max_0"],
                rows=[[10, 10, date(2025, 1, 5), date(2025, 3, 28)]],
                row_count=1,
                duration_ms=5,
            )
        if query.startswith("SELECT count(*) AS n"):
            raise ConnectorError("query_timeout", "The query took too long.")
        if query == 'SELECT count(*) FROM "shop"."stores"':
            raise ConnectorError("query_timeout", "The query took too long.")
        return real(query, *args, **kwargs)

    monkeypatch.setattr(ctx.connector, "run_query", slow)
    _run(ctx)
    stores = store.get_entry(db_session, ctx.version_id, "table.shop.stores")
    assert stores is not None and stores.details["row_estimate"] is None
    span = store.get_entry(db_session, ctx.version_id, "data_range.shop.orders")
    assert span is not None and span.details["exact"] is False
    assert (
        "info",
        "orders took too long to read in full, so I measured its dates on a sample.",
    ) in said
    timeouts = db_session.scalars(
        select(QueryRun).where(QueryRun.learning_run_id == ctx.run_id, QueryRun.status == "timeout")
    ).all()
    assert {row.purpose for row in timeouts} >= {
        "Count the rows of shop.stores",
        "Measure the dates of shop.orders",
    }
