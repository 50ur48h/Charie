"""Recipe writing, testing and saving on shop data (P09.3c, fake AI)."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from charie.learner.steps import recipes
from charie.learner.steps.base import StepContext
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.knowledge import store, versions
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.sources import DocFact, Document, DocumentSection


@pytest.fixture()
def practice_shop(db):
    """The practice shop schema with a stub connector for recipe test runs."""
    engine = create_engine(db)
    path = Path(__file__).resolve().parents[2] / "data" / "shop_db.sql"
    code = "\n".join(
        line for line in path.read_text().splitlines() if not line.strip().startswith("--")
    )
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS shop CASCADE"))
        for statement in code.split(";"):
            if statement.strip():
                conn.execute(text(statement))

    def run(sql: str):
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("BEGIN READ ONLY"))
            try:
                result = conn.execute(text(sql))
                return SimpleNamespace(
                    columns=list(result.keys()),
                    rows=[tuple(row) for row in result.all()],
                )
            finally:
                conn.execute(text("ROLLBACK"))

    class _StubConnector:
        def run_query(self, sql: str):
            started = time.monotonic()
            result = run(sql)
            return SimpleNamespace(
                rows=result.rows,
                row_count=len(result.rows),
                duration_ms=int((time.monotonic() - started) * 1000),
            )

    yield _StubConnector()
    engine.dispose()


def _seed(db_session) -> int:
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    for key, kind, title, meaning, details in [
        (
            "table.shop.orders",
            "table",
            "orders",
            "One row per order the shop took.",
            {"schema": "shop", "name": "orders", "primary_key": ["id"]},
        ),
        (
            "column.shop.orders.total_amount",
            "column",
            "total_amount",
            "What the customer paid, in dollars.",
            {
                "schema": "shop",
                "table": "orders",
                "name": "total_amount",
                "data_type": "numeric",
                "unit": "money",
                "currency": "USD",
            },
        ),
        (
            "column.shop.orders.status",
            "column",
            "status",
            "How the order ended.",
            {"schema": "shop", "table": "orders", "name": "status", "data_type": "text"},
        ),
        (
            "column.shop.orders.created_at",
            "column",
            "created_at",
            "When the order happened.",
            {
                "schema": "shop",
                "table": "orders",
                "name": "created_at",
                "data_type": "timestamp with time zone",
            },
        ),
        (
            "column.shop.orders.id",
            "column",
            "id",
            "The order number.",
            {"schema": "shop", "table": "orders", "name": "id", "data_type": "integer"},
        ),
        (
            "data_range.shop.orders",
            "data_range",
            "orders range",
            "The months the shop data covers.",
            {
                "table": "shop.orders",
                "date_column": "created_at",
                "date_from": "2025-11-01",
                "date_to": "2025-12-31",
            },
        ),
        (
            "dimension.month",
            "dimension",
            "month",
            "The month the order happened in.",
            {
                "kind": "time",
                "table": "shop.orders",
                "column": "created_at",
                "grain": "month",
                "unique_with": [],
            },
        ),
    ]:
        store.upsert_entry(
            db_session,
            version_id,
            key,
            kind,
            title,
            meaning,
            details,
            "checked",
            [{"type": "structure", "text": "Read from the database structure"}],
            "seed",
        )
    doc = Document(
        file_name="report.md", file_type="md", size_bytes=10, sha256="abc", status="learned"
    )
    db_session.add(doc)
    db_session.flush()
    section = DocumentSection(document_id=doc.id, position=0, text_="Net sales were $224.00.")
    db_session.add(section)
    db_session.flush()
    db_session.add(
        DocFact(
            document_id=doc.id,
            section_id=section.id,
            kind="reported_number",
            topic="Net sales",
            statement="Net sales were $224.00 in December 2025.",
            quote="Net sales were $224.00 in December 2025.",
            status="ok",
        )
    )
    db_session.commit()
    return version_id


def _proposal(**overrides) -> dict:
    recipe = {
        "term": "term.net_sales",
        "kind": "simple",
        "table": "shop.orders",
        "aggregate": "sum",
        "expression": "orders.total_amount",
        "filters": ["orders.status = 'completed'"],
        "time_column": "orders.created_at",
        "unit": "money",
        "currency": "USD",
        "steps_in_words": ["Add up every completed order total.", "Leave out delivery fees."],
        "dimensions": ["dimension.month"],
    }
    recipe.update(overrides)
    return recipe


def _term(**overrides) -> dict:
    term = {
        "key": "term.net_sales",
        "name": "Net sales",
        "meaning": "Completed order totals without delivery fees.",
        "unit": "money",
        "evidence": ["column:shop.orders.total_amount"],
        "splits": ["by month"],
        "dimensions": ["dimension.month"],
    }
    term.update(overrides)
    return term


def _ctx(db_session, version_id: int, connector):
    run = LearningRun(
        kind="first", status="running", step="business_numbers", version_id=version_id
    )
    db_session.add(run)
    db_session.commit()
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    ctx = StepContext(
        session=db_session,
        run_id=run.id,
        version_id=version_id,
        source=None,  # was shop_db["source"],
        connector=connector,
        strict_mode=False,
        settings={},
        say=say,
    )
    return ctx, said


def _run(ctx, monkeypatch, reply: dict) -> FakeAi:
    fake = FakeAi().reply("write_term_recipe", reply)
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(recipes, "get_ai", lambda: client)
    kept, failures = recipes.discover_and_test(ctx, [_term()])
    return fake, kept, failures


def test_four_checks(db_session, practice_shop, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, said = _ctx(db_session, version_id, practice_shop)
    fake, kept, failures = _run(ctx, monkeypatch, {"recipes": [_proposal()]})
    assert kept == 1
    assert failures == []
    entry = store.get_entry(db_session, version_id, "metric.net_sales")
    assert entry is not None
    assert entry.confidence == "checked"
    by_name = {check["name"]: check for check in entry.details["tests"]}
    assert sorted(by_name) == ["believable", "matches_documents", "parts_add_up", "runs"]
    assert all(check["passed"] is True for check in by_name.values())
    assert len(entry.details["reported_checks"]) == 1
    assert "224" in entry.details["reported_checks"][0]["number_text"]
    assert entry.details["sql_preview"].startswith("SELECT")
    assert entry.details["tested_at"]


def test_missing_comparison_fact_is_not_a_pass(db_session, practice_shop, monkeypatch) -> None:
    version_id = _seed(db_session)
    db_session.execute(text("UPDATE doc_facts SET statement = 'Refunds were $5 in November 2025.'"))
    ctx, _ = _ctx(db_session, version_id, practice_shop)
    _, kept, failures = _run(ctx, monkeypatch, {"recipes": [_proposal()]})
    assert kept == 1
    assert failures == []
    entry = store.get_entry(db_session, version_id, "metric.net_sales")
    by_name = {check["name"]: check for check in entry.details["tests"]}
    assert by_name["matches_documents"]["passed"] is None
    assert entry.details["reported_checks"] == []
    assert entry.confidence == "checked"


def test_failed_not_usable(db_session, practice_shop, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, _ = _ctx(db_session, version_id, practice_shop)
    bad = _proposal(expression="orders.nope")
    fake = FakeAi()
    for _ in range(3):
        fake.reply("write_term_recipe", {"recipes": [bad]})
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(recipes, "get_ai", lambda: client)
    kept, failures = recipes.discover_and_test(ctx, [_term()])
    assert kept == 0
    assert len(fake.calls) == 3
    assert failures and failures[0]["term"] == "term.net_sales"
    assert store.get_entry(db_session, version_id, "metric.net_sales") is None


def test_repair_bound(db_session, practice_shop, monkeypatch) -> None:
    version_id = _seed(db_session)
    ctx, _ = _ctx(db_session, version_id, practice_shop)
    fake = FakeAi()
    for _ in range(3):
        fake.reply("write_term_recipe", {"recipes": [_proposal(expression="orders.nope")]})
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(recipes, "get_ai", lambda: client)
    kept, _ = recipes.discover_and_test(ctx, [_term()])
    assert kept == 0
    assert len([call for call in fake.calls if call[0] == "write_term_recipe"]) == 3


def test_retest_affected_only(db_session, practice_shop) -> None:
    version_id = _seed(db_session)
    seen: list[str] = []

    def run(sql: str):
        seen.append(sql)
        return practice_shop.run_query(sql).rows

    def seed_recipe(key: str, title: str, expression: str) -> None:
        store.upsert_entry(
            db_session,
            version_id,
            key,
            "metric",
            title,
            "Seeded.",
            {
                "kind": "simple",
                "title": title,
                "table": "shop.orders",
                "aggregate": "sum" if "total" in expression else "count",
                "expression": expression,
                "filters": ["orders.status = 'completed'"] if "total" in expression else [],
                "time_column": "orders.created_at",
                "time_column_type": "timestamptz",
                "unit": "money" if "total" in expression else "count",
                "currency": "USD" if "total" in expression else "",
                "steps_in_words": ["Add them up.", "Only completed ones count."],
                "dimensions": [],
                "tests": [
                    {"name": "runs", "passed": True, "text": "seed"},
                    {"name": "believable", "passed": True, "text": "seed"},
                    {"name": "matches_documents", "passed": None, "text": "seed"},
                    {"name": "parts_add_up", "passed": True, "text": "seed"},
                ],
                "reported_checks": [],
                "sql_preview": "seed",
                "tested_at": "2000-01-01T00:00:00+00:00",
            },
            "checked",
            [{"type": "structure", "text": "seed"}],
            "seed",
        )

    db_session.commit()
    seed_recipe("metric.net_sales", "Net sales", "orders.total_amount")
    seed_recipe("metric.order_count", "Order count", "orders.id")
    db_session.commit()
    outcome = recipes.retest_affected(db_session, version_id, ["shop.orders.total_amount"], run)
    assert outcome == {"metric.net_sales": True}
    assert not any("COUNT(orders.id)" in sql for sql in seen)
    assert any("SUM(orders.total_amount)" in sql for sql in seen)
    assert (
        store.get_entry(db_session, version_id, "metric.order_count").details["tested_at"]
        == "2000-01-01T00:00:00+00:00"
    )
    assert (
        store.get_entry(db_session, version_id, "metric.net_sales").details["tested_at"]
        != "2000-01-01T00:00:00+00:00"
    )
