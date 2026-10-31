"""Self-test practice questions with an independent examiner (P09.8)."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from charie.learner.steps import self_test
from charie.learner.steps.base import StepContext
from charie.learner.steps.self_test import PracticeQuestionDraft, finish_step, practice_one
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.knowledge import sql_writer, store, versions
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import OwnerQuestion


@pytest.fixture()
def practice_shop(db):
    """The practice shop schema with a columns-and-rows runner."""
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

    yield run
    engine.dispose()


@pytest.fixture()
def version_id(db_session):
    return versions.get_or_create_draft(db_session, "first_learning").id


def _seed(db_session, version_id: int, gross_ok: bool = True) -> None:
    store.upsert_entry(
        db_session,
        version_id,
        "table.shop.orders",
        "table",
        "orders",
        "orders",
        {"schema": "shop", "name": "orders", "primary_key": ["id"]},
        "checked",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )
    for key, title, filters, ok in [
        ("metric.net_sales", "Net sales", ["orders.status = 'completed'"], True),
        ("metric.gross_sales", "Gross sales", [], gross_ok),
    ]:
        store.upsert_entry(
            db_session,
            version_id,
            key,
            "metric",
            title,
            title,
            {
                "kind": "simple",
                "title": title,
                "table": "shop.orders",
                "aggregate": "sum",
                "expression": "orders.total_amount",
                "filters": filters,
                "time_column": "orders.created_at",
                "time_column_type": "timestamptz",
                "unit": "money",
                "currency": "USD",
                "steps_in_words": ["Add them up.", "Keep the kept rows."],
                "dimensions": [],
                "tests": [
                    {"name": "runs", "passed": True, "text": "seed"},
                    {"name": "believable", "passed": True, "text": "seed"},
                    {
                        "name": "matches_documents",
                        "passed": ok,
                        "text": "seed" if ok else "The documents disagree.",
                    },
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


def _draft() -> PracticeQuestionDraft:
    return PracticeQuestionDraft(
        question="What were net sales in November 2025?",
        metric="metric.net_sales",
        period_start="2025-11-01",
        period_end="2025-11-30",
        splits=[],
    )


def _fake(monkeypatch, examiner_sql: str) -> FakeAi:
    fake = FakeAi().reply(
        "write_practice_questions",
        {
            "questions": [
                {
                    "question": "What were net sales in November 2025?",
                    "metric": "metric.net_sales",
                    "period_start": "2025-11-01",
                    "period_end": "2025-11-30",
                    "splits": [],
                }
            ]
        },
    )
    fake.reply("write_sql", {"sql": examiner_sql, "notes": "Net sales."})
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(self_test, "get_ai", lambda: client)
    monkeypatch.setattr(sql_writer, "get_ai", lambda: client)
    return fake


def _examiner(where: str) -> str:
    return (
        "SELECT SUM(orders.total_amount) AS total FROM shop.orders AS orders WHERE "
        f"{where} AND orders.created_at >= '2025-11-01 00:00:00 America/Chicago' "
        "AND orders.created_at < '2025-12-01 00:00:00 America/Chicago'"
    )


def _ctx(db_session, version_id: int, outcomes: list[dict]):
    run = LearningRun(kind="first", status="running", step="self_test", version_id=version_id)
    db_session.add(run)
    db_session.commit()
    run.progress = {"self_test": {"requested": len(outcomes), "outcomes": outcomes}}
    db_session.commit()
    said: list = []

    def say(kind: str, message: str, details=None) -> None:
        said.append((kind, message))

    return (
        StepContext(
            session=db_session,
            run_id=run.id,
            version_id=version_id,
            source=None,
            connector=None,
            strict_mode=False,
            settings={},
            say=say,
        ),
        said,
    )


def test_disagreement_topic(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed(db_session, version_id)
    fake = _fake(monkeypatch, _examiner("1 = 1"))
    outcome = practice_one(db_session, version_id, _draft(), practice_shop, "America/Chicago", None)
    assert outcome["status"] == "wrong", outcome["reason"]
    assert [call[0] for call in fake.calls] == ["write_sql"]
    ctx, _ = _ctx(db_session, version_id, [outcome])
    finish_step(ctx)
    entry = store.get_entry(db_session, version_id, "metric.net_sales")
    assert entry.confidence == "guessed"
    assert any(
        check.get("name") == "self_test" and check.get("passed") is False
        for check in entry.details["tests"]
    )
    from charie.learner.steps import recipes as recipes_step

    assert any(
        failure["key"] == "metric.net_sales"
        for failure in recipes_step.failed_recipes(db_session, version_id)
    )
    readiness = db_session.get(KbVersion, version_id).readiness
    assert readiness["practice_right"] == 0
    assert readiness["practice_total"] == 1
    assert readiness["weak_area"] == "Net sales"


def test_unrun_not_pass(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed(db_session, version_id)
    _fake(monkeypatch, "SELECT * FROM shop.secrets")
    outcome = practice_one(db_session, version_id, _draft(), practice_shop, "America/Chicago", None)
    assert outcome["status"] == "unrun", outcome["reason"]
    ctx, _ = _ctx(db_session, version_id, [outcome])
    finish_step(ctx)
    readiness = db_session.get(KbVersion, version_id).readiness
    assert readiness["practice_total"] == 1
    assert readiness["practice_right"] == 0
    right = sum(1 for item in readiness["outcomes"] if item["status"] == "match")
    wrong = sum(1 for item in readiness["outcomes"] if item["status"] == "wrong")
    unrun = sum(1 for item in readiness["outcomes"] if item["status"] == "unrun")
    assert (right, wrong, unrun) == (0, 0, 1)
    assert right + wrong + unrun == readiness["practice_total"]


def test_readiness_counts(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed(db_session, version_id, gross_ok=False)
    db_session.add(
        OwnerQuestion(
            status="waiting",
            rank=1,
            importance=1,
            topic="How to fix Gross sales",
            title="How to fix Gross sales?",
            body="Gross sales failed a check.",
            evidence={"origin": "recipe", "sources": []},
            options=[],
            default_option="",
            affects=["metric.gross_sales"],
            source="learning",
        )
    )
    db_session.commit()
    _fake(monkeypatch, _examiner("orders.status = 'completed'"))
    outcome = practice_one(db_session, version_id, _draft(), practice_shop, "America/Chicago", None)
    assert outcome["status"] == "match", outcome["reason"]
    ctx, _ = _ctx(db_session, version_id, [outcome])
    finish_step(ctx)
    readiness = db_session.get(KbVersion, version_id).readiness
    assert readiness["numbers_checked"] == 1
    assert readiness["numbers_total"] == 2
    assert readiness["numbers_waiting"] == 1
    assert readiness["practice_right"] == 1
    assert readiness["practice_total"] == 1
    assert readiness["weak_area"] is None
    assert readiness["unchecked_metrics"] == ["metric.gross_sales"]
    assert readiness["pending_topics"] == ["How to fix Gross sales"]
    assert readiness["learned_at"]


def test_replay_no_network(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed(db_session, version_id)
    fake = _fake(monkeypatch, _examiner("orders.status = 'completed'"))
    drafts = self_test.generate_questions(db_session, version_id, 50, None)
    assert len(drafts) == 1
    outcome = practice_one(
        db_session, version_id, drafts[0], practice_shop, "America/Chicago", None
    )
    assert outcome["status"] == "match", outcome["reason"]
    assert [call[0] for call in fake.calls] == ["write_practice_questions", "write_sql"]


def test_invalid_mapping_rejected(db_session, version_id) -> None:
    _seed(db_session, version_id)
    bad = PracticeQuestionDraft(
        question="What were nothing?",
        metric="metric.missing",
        period_start="2025-11-01",
        period_end="2025-11-30",
        splits=[],
    )
    assert self_test.valid_mapping(db_session, version_id, bad) is not None
    flipped = PracticeQuestionDraft(
        question="What were net sales?",
        metric="metric.net_sales",
        period_start="2025-12-01",
        period_end="2025-11-01",
        splits=[],
    )
    assert self_test.valid_mapping(db_session, version_id, flipped) is not None
    assert self_test.valid_mapping(db_session, version_id, _draft()) is None
