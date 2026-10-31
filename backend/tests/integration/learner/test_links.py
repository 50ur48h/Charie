"""Step 4 finds and tests the links between tables (P07.8)."""

import pytest
from sqlalchemy import text

from charie.learner.steps import links
from charie.learner.steps.base import StepContext
from charie.learner.steps.structure import run_job as run_structure
from charie.shared.connectors.base import ConnectorError
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.knowledge.catalog import build_catalog
from charie.shared.safety.sql_check import check_sql
from charie.shared.tables.learning import LearningRun


@pytest.fixture()
def links_ctx(db_session, shop_db):
    """The shop scanned, ready to link."""
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="links", version_id=version_id)
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
    return ctx, said


def _run(ctx, **payload) -> None:
    links.run_job(
        JobInfo(id=2, kind="test_link", payload={"step": "links", **payload}, run_id=ctx.run_id),
        ctx,
    )


def _link(db_session, version_id: int, key: str):
    entry = store.get_entry(db_session, version_id, key)
    assert entry is not None
    return entry


def test_make_jobs_finds_five_candidates(links_ctx) -> None:
    ctx, _ = links_ctx
    jobs = links.make_jobs(ctx)
    assert {
        (job["from_table"], ",".join(job["from_columns"]), job["to_table"], job["via"])
        for job in jobs
    } == {
        ("shop.orders", "store_id", "shop.stores", "fk"),
        ("shop.order_lines", "order_id", "shop.orders", "fk"),
        ("shop.order_notes", "order_id", "shop.orders", "fk"),
        ("shop.orders", "coupon_code", "shop.coupons", "name"),
        ("shop.stores", "city_id", "shop.cities", "name"),
    }


def test_foreign_key_link_is_checked(links_ctx, db_session) -> None:
    ctx, said = links_ctx
    _run(
        ctx,
        from_table="shop.order_lines",
        from_columns=["order_id"],
        to_table="shop.orders",
        to_columns=["id"],
        via="fk",
    )
    entry = _link(db_session, ctx.version_id, "link.shop.order_lines.order_id~shop.orders.id")
    assert entry.confidence == "checked"
    assert entry.title == "order_lines.order_id → orders.id"
    assert entry.meaning == (
        "Each row of order_lines points to one row of orders, through order_id."
        " Many rows can point to the same row. Tested: 100% of rows match."
    )
    assert entry.details["cardinality"] == "many_to_one"
    assert entry.details["found_by"] == "foreign_key"
    assert entry.details["match_share"] == 1.0
    assert entry.details["orphans"] == 0
    assert entry.details["sampled"] is False
    assert [source["type"] for source in entry.sources] == ["query", "structure"]
    assert ("found", "Linked order_lines to orders through order_id: 100% of rows match.") in said


def test_one_to_one_link(links_ctx, db_session) -> None:
    ctx, _ = links_ctx
    _run(
        ctx,
        from_table="shop.order_notes",
        from_columns=["order_id"],
        to_table="shop.orders",
        to_columns=["id"],
        via="fk",
    )
    entry = _link(db_session, ctx.version_id, "link.shop.order_notes.order_id~shop.orders.id")
    assert entry.confidence == "checked"
    assert entry.details["cardinality"] == "one_to_one"
    assert entry.meaning == (
        "Each row of order_notes matches at most one row of orders, through order_id."
        " Tested: 100% of rows match."
    )


def test_name_match_kept_as_a_guess(links_ctx, db_session) -> None:
    ctx, said = links_ctx
    _run(
        ctx,
        from_table="shop.orders",
        from_columns=["coupon_code"],
        to_table="shop.coupons",
        to_columns=["code"],
        via="name",
    )
    entry = _link(db_session, ctx.version_id, "link.shop.orders.coupon_code~shop.coupons.code")
    assert entry.confidence == "guessed"
    assert entry.details["found_by"] == "matching_name"
    assert entry.details["match_share"] == 0.9
    assert (
        "warning",
        "orders.coupon_code matches coupons.code for only 90% of rows. I'll keep it as a guess.",
    ) in said


def test_bad_candidate_is_dropped(links_ctx, db_session) -> None:
    ctx, said = links_ctx
    _run(
        ctx,
        from_table="shop.stores",
        from_columns=["city_id"],
        to_table="shop.cities",
        to_columns=["id"],
        via="name",
    )
    assert (
        store.get_entry(db_session, ctx.version_id, "link.shop.stores.city_id~shop.cities.id")
        is None
    )
    assert (
        "info",
        "stores.city_id looked like a link to cities, but only 33% of rows match, so it isn't one.",
    ) in said


def test_rerun_removes_a_dead_link(links_ctx, db_session, shop_db) -> None:
    ctx, _ = links_ctx
    _run(
        ctx,
        from_table="shop.orders",
        from_columns=["coupon_code"],
        to_table="shop.coupons",
        to_columns=["code"],
        via="name",
    )
    key = "link.shop.orders.coupon_code~shop.coupons.code"
    assert store.get_entry(db_session, ctx.version_id, key) is not None
    with shop_db["owner"].begin() as conn:
        conn.execute(text("ALTER TABLE shop.orders DROP COLUMN coupon_code"))
    run_structure(
        JobInfo(id=3, kind="scan_structure", payload={"step": "structure"}, run_id=ctx.run_id),
        ctx,
    )
    links.finish_step(ctx)
    gone = store.get_entry(db_session, ctx.version_id, key)
    assert gone is None


def test_catalog_gets_one_to_many_links(links_ctx, db_session) -> None:
    ctx, _ = links_ctx
    for job in links.make_jobs(ctx):
        _run(ctx, **job)
    catalog = build_catalog(db_session, ctx.version_id)
    assert {(link.one_table, link.many_table) for link in catalog.links} == {
        ("shop.orders", "shop.order_lines"),
        ("shop.stores", "shop.orders"),
    }
    # The one-to-one order_notes link is kept, but never fans rows out.
    assert (
        store.get_entry(db_session, ctx.version_id, "link.shop.order_notes.order_id~shop.orders.id")
        is not None
    )


def test_checker_blocks_double_counting(links_ctx, db_session) -> None:
    ctx, _ = links_ctx
    for job in links.make_jobs(ctx):
        _run(ctx, **job)
    catalog = build_catalog(db_session, ctx.version_id)
    blocked = check_sql(
        "SELECT SUM(o.total) FROM shop.orders o JOIN shop.order_lines l ON l.order_id = o.id",
        catalog,
    )
    assert not blocked.ok
    assert blocked.rules == ["double_counting"]
    passing = check_sql(
        "SELECT SUM(l.qty) FROM shop.order_lines l JOIN shop.orders o ON l.order_id = o.id",
        catalog,
    )
    assert passing.ok, passing.reasons


def test_finish_counts_links(links_ctx) -> None:
    ctx, said = links_ctx
    for job in links.make_jobs(ctx):
        _run(ctx, **job)
    links.finish_step(ctx)
    assert said[-1] == ("found", "4 links between tables (3 checked)")


def test_composite_nulls_do_not_hide_fan_out(links_ctx, db_session, shop_db) -> None:
    ctx, _ = links_ctx
    with shop_db["owner"].begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE shop.review_parent (tenant integer, code integer,"
                " amount numeric, PRIMARY KEY (tenant, code))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE shop.review_child (id integer PRIMARY KEY, tenant integer,"
                " code integer, FOREIGN KEY (tenant, code)"
                " REFERENCES shop.review_parent (tenant, code))"
            )
        )
        conn.execute(text("INSERT INTO shop.review_parent VALUES (1, 1, 10)"))
        conn.execute(
            text("INSERT INTO shop.review_child VALUES (1, 1, 1), (2, 1, 1), (3, NULL, 2)")
        )
        conn.execute(
            text(
                "GRANT SELECT ON shop.review_parent, shop.review_child"
                f' TO "{ctx.connector.username}"'
            )
        )
    run_structure(
        JobInfo(id=3, kind="scan_structure", payload={"step": "structure"}, run_id=ctx.run_id),
        ctx,
    )
    _run(
        ctx,
        from_table="shop.review_child",
        from_columns=["tenant", "code"],
        to_table="shop.review_parent",
        to_columns=["tenant", "code"],
        via="fk",
    )
    entry = store.get_entry(
        db_session,
        ctx.version_id,
        "link.shop.review_child.tenant+code~shop.review_parent.tenant+code",
    )
    assert entry is not None
    assert entry.details["cardinality"] == "many_to_one"
    catalog = build_catalog(db_session, ctx.version_id)
    blocked = check_sql(
        "SELECT SUM(p.amount) FROM shop.review_parent p JOIN shop.review_child c"
        " ON (c.tenant, c.code) = (p.tenant, p.code)",
        catalog,
    )
    assert not blocked.ok
    assert blocked.rules == ["double_counting"]


def test_slow_link_falls_back_to_valid_sampled_sql(links_ctx, monkeypatch) -> None:
    ctx, _ = links_ctx
    real = ctx.connector.run_query
    seen: list[str] = []

    def flaky(sql, *args, **kwargs):
        seen.append(sql)
        if "AS empty_from" in sql and "TABLESAMPLE" not in sql:
            raise ConnectorError("query_timeout", "Synthetic timeout, without waiting.")
        return real(sql, *args, **kwargs)

    monkeypatch.setattr(ctx.connector, "run_query", flaky)
    links.run_job(
        JobInfo(
            id=4,
            kind="test_link",
            payload={
                "step": "links",
                "from_table": "shop.order_lines",
                "from_columns": ["order_id"],
                "to_table": "shop.orders",
                "to_columns": ["id"],
                "via": "fk",
            },
            run_id=ctx.run_id,
        ),
        ctx,
    )
    fallback = next(sql for sql in seen if "TABLESAMPLE" in sql)
    rows = real(fallback).rows
    assert len(rows) == 1 and len(rows[0]) == 4
