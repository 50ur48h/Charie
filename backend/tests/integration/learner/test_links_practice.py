"""Step 4 on the real practice database: the main links test checked (P07.8).

Laptop only: needs `PRACTICE_DB_URL`. Never writes to the practice data;
links land in the throwaway database. Stays quick by testing only the
candidates between `orders`, `order_items`, `menu_items` and `restaurants`.
"""

import pytest

from charie.learner.steps import links
from charie.learner.steps.base import StepContext
from charie.learner.steps.structure import run_job as run_structure
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.knowledge.catalog import build_catalog
from charie.shared.safety.sql_check import check_sql
from charie.shared.tables.learning import LearningRun

TABLES = {"public.orders", "public.order_items", "public.menu_items", "public.restaurants"}


@pytest.fixture()
def practice_ctx(db_session, practice_source):
    """A step context on the throwaway database with the practice connected."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="links", version_id=version_id)
    db_session.add(run)
    db_session.commit()
    said: list = []
    return (
        StepContext(
            session=db_session,
            run_id=run.id,
            version_id=version_id,
            source=practice_source["source"],
            connector=practice_source["connector"],
            strict_mode=False,
            settings={},
            say=lambda kind, message, details=None: said.append((kind, message)),
        ),
        said,
    )


def _run(ctx, **payload) -> None:
    links.run_job(
        JobInfo(id=2, kind="test_link", payload={"step": "links", **payload}, run_id=ctx.run_id),
        ctx,
    )


def _main_candidates(ctx):
    run_structure(
        JobInfo(id=1, kind="scan_structure", payload={"step": "structure"}, run_id=ctx.run_id),
        ctx,
    )
    return [
        job
        for job in links.make_jobs(ctx)
        if job["from_table"] in TABLES and job["to_table"] in TABLES
    ]


@pytest.mark.practice_db
def test_main_practice_links_are_tested(practice_ctx, db_session) -> None:
    ctx, _ = practice_ctx
    jobs = _main_candidates(ctx)
    assert {
        (job["from_table"], ",".join(job["from_columns"]), job["to_table"]) for job in jobs
    } >= {
        ("public.orders", "restaurant_id", "public.restaurants"),
        ("public.order_items", "order_id", "public.orders"),
        ("public.order_items", "menu_item_id", "public.menu_items"),
    }
    for job in jobs:
        _run(ctx, **job)
    for from_table, column, to_table in (
        ("public.orders", "restaurant_id", "public.restaurants"),
        ("public.order_items", "order_id", "public.orders"),
        ("public.order_items", "menu_item_id", "public.menu_items"),
    ):
        to_key = {"public.restaurants": "id", "public.orders": "id", "public.menu_items": "id"}[
            to_table
        ]
        key = f"link.{from_table}.{column}~{to_table}.{to_key}"
        entry = store.get_entry(db_session, ctx.version_id, key)
        assert entry is not None
        assert entry.confidence == "checked"
        assert entry.details["cardinality"] == "many_to_one"


@pytest.mark.practice_db
def test_checker_blocks_double_counting_with_real_links(practice_ctx, db_session) -> None:
    ctx, _ = practice_ctx
    for job in _main_candidates(ctx):
        _run(ctx, **job)
    catalog = build_catalog(db_session, ctx.version_id)
    blocked = check_sql(
        "SELECT SUM(o.total_amount) FROM public.orders o"
        " JOIN public.order_items i ON i.order_id = o.id",
        catalog,
    )
    assert not blocked.ok
    assert blocked.rules == ["double_counting"]
    passing = check_sql(
        "SELECT SUM(i.quantity) FROM public.order_items i"
        " JOIN public.orders o ON i.order_id = o.id",
        catalog,
    )
    assert passing.ok, passing.reasons
