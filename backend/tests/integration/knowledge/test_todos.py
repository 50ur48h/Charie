"""The learner to-do list: queue, dismiss, handle, retry (P09.7, fake AI)."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, text

from charie.learner.steps import todos as todos_step
from charie.learner.steps.base import StepContext
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.knowledge import questions, store, versions
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import LearnerTodo, OwnerQuestion
from charie.shared.tables.sources import DocFact, Document, DocumentSection
from tests.conftest import log_in


@pytest.fixture()
def practice_shop(db):
    """The practice shop schema with a stub connector for retests."""
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
                return [tuple(row) for row in result.all()]
            finally:
                conn.execute(text("ROLLBACK"))

    class _StubConnector:
        def run_query(self, sql: str):
            started = time.monotonic()
            rows = run(sql)
            return SimpleNamespace(
                rows=rows,
                row_count=len(rows),
                duration_ms=int((time.monotonic() - started) * 1000),
            )

    yield _StubConnector()
    engine.dispose()


@pytest.fixture()
def version_id(db_session):
    return versions.get_or_create_draft(db_session, "first_learning").id


def _seed_metrics(db_session, version_id: int) -> None:
    for key, kind, title, details in [
        (
            "table.shop.orders",
            "table",
            "orders",
            {"schema": "shop", "name": "orders", "primary_key": ["id"]},
        ),
        (
            "column.shop.orders.total_amount",
            "column",
            "total_amount",
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
            {"schema": "shop", "table": "orders", "name": "status", "data_type": "text"},
        ),
        (
            "column.shop.orders.created_at",
            "column",
            "created_at",
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
            {"schema": "shop", "table": "orders", "name": "id", "data_type": "integer"},
        ),
        (
            "data_range.shop.orders",
            "data_range",
            "orders range",
            {
                "table": "shop.orders",
                "date_column": "created_at",
                "date_from": "2025-11-01",
                "date_to": "2025-12-31",
            },
        ),
    ]:
        store.upsert_entry(
            db_session,
            version_id,
            key,
            kind,
            title,
            title,
            details,
            "checked",
            [{"type": "structure", "text": "seed"}],
            "seed",
        )
    for key, title, filters in [
        ("metric.net_sales", "Net sales", ["orders.status = 'completed'"]),
        ("metric.gross_sales", "Gross sales", []),
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


def _seed_conflict_fact(db_session) -> None:
    doc = Document(
        file_name="report.md", file_type="md", size_bytes=10, sha256="abc", status="learned"
    )
    db_session.add(doc)
    db_session.flush()
    section = DocumentSection(document_id=doc.id, position=0, text_="Net sales were $999.")
    db_session.add(section)
    db_session.flush()
    db_session.add(
        DocFact(
            document_id=doc.id,
            section_id=section.id,
            kind="reported_number",
            topic="Net sales",
            statement="Net sales were $999 in November 2025.",
            quote="Net sales were $999 in November 2025.",
            status="ok",
        )
    )
    db_session.commit()


def _ctx(db_session, version_id: int, practice_shop) -> StepContext:
    run = LearningRun(kind="first", status="running", step="owner_notes", version_id=version_id)
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
        connector=practice_shop,
        strict_mode=False,
        settings={},
        say=say,
    )


def _question_reply() -> dict:
    return {
        "questions": [
            {
                "topic": "How to fix Net sales",
                "title": "How net sales should be worked out",
                "body": "The recipe failed its checks.",
                "options": [
                    {
                        "id": "a",
                        "label": "Completed orders",
                        "explanation": "Leave out cancelled ones.",
                        "proposal": {"metric": "metric.net_sales"},
                    },
                    {
                        "id": "b",
                        "label": "All orders",
                        "explanation": "Count everything.",
                        "proposal": {"metric": "metric.gross_sales"},
                    },
                ],
                "default_option": "b",
            }
        ]
    }


def _correction(
    db_session, key: str = "metric.net_sales", words: str = "Net sales looks too high."
) -> int:
    todo = LearnerTodo(
        kind="correction",
        text_=f"Net sales: {words}",
        details={"key": key, "words": words},
        status="open",
    )
    db_session.add(todo)
    db_session.commit()
    return todo.id


def test_wrong_only_queues(db_session, version_id, learner_client) -> None:
    _seed_metrics(db_session, version_id)
    log_in(learner_client)
    response = learner_client.post(
        "/api/knowledge/metric.net_sales/wrong", json={"note": "too high"}
    )
    assert response.status_code == 201, response.text
    todo = response.json()["todo"]
    assert todo["kind"] == "correction"
    assert todo["status"] == "open"
    assert todo["text"] == "Net sales: too high"
    assert todo["details"]["key"] == "metric.net_sales"
    entry = store.get_entry(db_session, version_id, "metric.net_sales")
    assert entry.confidence == "checked"
    assert entry.meaning == "Net sales"


def test_dismiss(db_session, version_id, learner_client) -> None:
    _seed_metrics(db_session, version_id)
    log_in(learner_client)
    created = learner_client.post("/api/knowledge/metric.net_sales/wrong", json={})
    todo_id = created.json()["todo"]["id"]
    missing = learner_client.post("/api/todos/999999/dismiss")
    assert missing.status_code == 404
    response = learner_client.post(f"/api/todos/{todo_id}/dismiss")
    assert response.status_code == 200, response.text
    shown = response.json()["todo"]
    assert shown["status"] == "dismissed"
    assert shown["result"] == "Dismissed by you"
    assert shown["done_at"] is not None
    again = learner_client.post(f"/api/todos/{todo_id}/dismiss")
    assert again.status_code == 200
    entry = store.get_entry(db_session, version_id, "metric.net_sales")
    assert entry.confidence == "checked"


def test_correction_question(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed_metrics(db_session, version_id)
    _seed_conflict_fact(db_session)
    _correction(db_session)
    fake = FakeAi().reply("write_owner_questions", _question_reply())
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(questions, "get_ai", lambda: client)
    summary = todos_step.handle_todos(_ctx(db_session, version_id, practice_shop))
    assert summary == {"done": 1, "questions": 1, "errors": []}
    todo = db_session.get(LearnerTodo, 1)
    assert todo.status == "done"
    assert todo.result == "Asked you: How net sales should be worked out."
    assert todo.done_at is not None
    rows = db_session.scalars(select(OwnerQuestion)).all()
    assert len(rows) == 1
    assert rows[0].status == "waiting"
    assert rows[0].evidence["origin"] == "todo"
    assert rows[0].topic == "How to fix Net sales"


def test_retry_atomic(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed_metrics(db_session, version_id)
    _seed_conflict_fact(db_session)
    _correction(db_session, words="First note.")
    _correction(db_session, words="Second note.")
    fake = FakeAi().reply("write_owner_questions", _question_reply())
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(questions, "get_ai", lambda: client)
    first = todos_step.handle_todos(_ctx(db_session, version_id, practice_shop))
    assert first["done"] == 1
    assert len(first["errors"]) == 1
    assert db_session.get(LearnerTodo, 1).status == "done"
    assert db_session.get(LearnerTodo, 2).status == "open"
    fake.reply("write_owner_questions", _question_reply())
    second = todos_step.handle_todos(_ctx(db_session, version_id, practice_shop))
    assert second == {"done": 1, "questions": 1, "errors": []}
    assert db_session.get(LearnerTodo, 2).status == "done"
    rows = db_session.scalars(select(OwnerQuestion).order_by(OwnerQuestion.id)).all()
    assert len(rows) == 2
    assert rows[0].evidence["fingerprint"] != rows[1].evidence["fingerprint"]
