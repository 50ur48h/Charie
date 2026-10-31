"""Default meanings: guessed topics, confirmed preservation, reruns (P09.4, fake AI)."""

import pytest

from charie.learner.steps import defaults
from charie.learner.steps.base import StepContext
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.knowledge import store, versions
from charie.shared.knowledge.defaults import default_topics
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.sources import OwnerNote


@pytest.fixture()
def version_id(db_session):
    return versions.get_or_create_draft(db_session, "first_learning").id


def _seed_metric(db_session, version_id: int) -> None:
    store.upsert_entry(
        db_session,
        version_id,
        "metric.net_sales",
        "metric",
        "Net sales",
        "Completed order totals.",
        {
            "kind": "simple",
            "title": "Net sales",
            "table": "shop.orders",
            "aggregate": "sum",
            "expression": "orders.total_amount",
            "filters": [],
            "time_column": "orders.created_at",
            "time_column_type": "timestamptz",
            "unit": "money",
            "currency": "USD",
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
    db_session.add(OwnerNote(text_="Sales means completed orders. A week is Monday to Sunday."))
    db_session.commit()


def _ctx(db_session, version_id: int) -> StepContext:
    run = LearningRun(kind="first", status="running", step="defaults", version_id=version_id)
    db_session.add(run)
    db_session.commit()
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    return StepContext(
        session=db_session,
        run_id=run.id,
        version_id=version_id,
        source=None,
        connector=None,
        strict_mode=False,
        settings={},
        say=say,
    )


def _run(ctx, monkeypatch, reply: dict) -> FakeAi:
    fake = FakeAi().reply("propose_defaults", reply)
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(defaults, "get_ai", lambda: client)
    return fake


def _proposal(**overrides) -> dict:
    base = {
        "word": "sales",
        "value": "metric.net_sales",
        "metrics": ["metric.net_sales"],
        "quote": "Sales means completed orders.",
    }
    base.update(overrides)
    return base


def _proposals() -> dict:
    return {
        "defaults": [
            _proposal(),
            _proposal(
                word="last_week",
                value="last_full_week",
                metrics=[],
                quote="A week is Monday to Sunday.",
            ),
            _proposal(word="best", value="", metrics=[], quote=""),
        ]
    }


def test_guessed_topics(db_session, version_id, monkeypatch) -> None:
    _seed_metric(db_session, version_id)
    ctx = _ctx(db_session, version_id)
    _run(ctx, monkeypatch, _proposals())
    kept, failures = defaults.discover_defaults(ctx)
    assert kept == 3
    assert failures == []
    topics = default_topics(db_session, version_id)
    assert [topic["entry_key"] for topic in topics] == [
        "default.best",
        "default.last_week",
        "default.sales",
    ]
    assert all(topic["origin"] == "default" for topic in topics)
    sales = next(topic for topic in topics if topic["entry_key"] == "default.sales")
    assert sales["metric_key"] == "metric.net_sales"
    assert sales["affects"] == ["metric.net_sales"]
    assert sales["context"]["proposed"] == "metric.net_sales"
    assert sales["context"]["safe"] == "metric.net_sales"
    best = next(topic for topic in topics if topic["entry_key"] == "default.best")
    assert best["metric_key"] == ""
    assert best["context"]["alternatives"] == ["metric.net_sales"]


def _seed_gross(db_session, version_id: int) -> None:
    store.upsert_entry(
        db_session,
        version_id,
        "metric.gross_sales",
        "metric",
        "Gross sales",
        "Everything before refunds.",
        {
            "kind": "simple",
            "title": "Gross sales",
            "table": "shop.orders",
            "aggregate": "sum",
            "expression": "orders.total_amount",
            "filters": [],
            "time_column": "orders.created_at",
            "time_column_type": "timestamptz",
            "unit": "money",
            "currency": "USD",
            "steps_in_words": ["Add them up.", "Keep every row."],
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


def test_confirmed_preserved(db_session, version_id, monkeypatch) -> None:
    _seed_metric(db_session, version_id)
    _seed_gross(db_session, version_id)
    store.upsert_entry(
        db_session,
        version_id,
        "default.sales",
        "default",
        "sales",
        "metric.net_sales",
        {
            "word": "sales",
            "value": "metric.net_sales",
            "evidence": [],
            "metrics": ["metric.net_sales"],
        },
        "confirmed",
        [{"type": "owner_notes", "quote": "Sales means completed orders."}],
        "owner confirmed",
    )
    db_session.commit()
    ctx = _ctx(db_session, version_id)
    _run(ctx, monkeypatch, {"defaults": [_proposal(value="metric.gross_sales")]})
    kept, failures = defaults.discover_defaults(ctx)
    assert kept == 0
    assert failures == []
    entry = store.get_entry(db_session, version_id, "default.sales")
    assert entry is not None
    assert entry.confidence == "confirmed"
    assert entry.details["value"] == "metric.net_sales"


def test_idempotent(db_session, version_id, monkeypatch) -> None:
    _seed_metric(db_session, version_id)
    ctx = _ctx(db_session, version_id)
    fake = _run(ctx, monkeypatch, _proposals())
    kept, _ = defaults.discover_defaults(ctx)
    assert kept == 3
    fake.reply("propose_defaults", _proposals())
    kept_again, _ = defaults.discover_defaults(ctx)
    assert kept_again == 3
    entries = store.list_entries(db_session, version_id, kinds=["default"])
    assert sorted(entry.key for entry in entries) == [
        "default.best",
        "default.last_week",
        "default.sales",
    ]
    assert defaults.make_jobs(ctx) == [{"step": "defaults"}]
    store.upsert_entry(
        db_session,
        version_id,
        "default.period",
        "default",
        "period",
        "latest_full_month",
        {"word": "period", "value": "latest_full_month", "evidence": [], "metrics": []},
        "guessed",
        [{"type": "ai", "text": "seed"}],
        "seed",
    )
    db_session.commit()
    assert defaults.make_jobs(ctx) == []
