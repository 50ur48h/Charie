"""Answering and skipping owner questions on real data (P09.6)."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select, text

from charie.shared.config import get_settings
from charie.shared.crypto import encrypt_text
from charie.shared.db import session_scope
from charie.shared.knowledge import store, versions
from charie.shared.knowledge.answers import (
    AnswerConflict,
    apply_answer,
)
from charie.shared.tables.questions import LearnerTodo, OwnerQuestion
from charie.shared.tables.sources import DataSource
from tests.conftest import log_in


@pytest.fixture()
def _enc_key(monkeypatch):
    """A fresh encryption key, never the real one."""
    monkeypatch.setenv("CHARIE_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def practice_source(db_session, _enc_key, db):
    """A source row pointing at the throwaway database holding shop data."""
    parts = urlparse(db)
    db_session.add(
        DataSource(
            kind="postgres",
            name="practice database",
            host=parts.hostname or "localhost",
            port=parts.port or 5432,
            database=parts.path.lstrip("/"),
            username=parts.username or "",
            password_encrypted=encrypt_text(parts.password or ""),
            status="connected",
            read_only_ok=True,
        )
    )
    db_session.commit()


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

    yield run
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
        "guessed",
        [{"type": "ai", "text": "seed"}],
        "seed",
    )
    db_session.commit()


def _ask_row(db_session, topic: str = "What sales means") -> int:
    row = OwnerQuestion(
        status="waiting",
        rank=1,
        importance=1,
        topic=topic,
        title="What should sales mean?",
        body="This decides which number sales questions use.",
        evidence={
            "origin": "default",
            "entry_key": "default.sales",
            "metric_key": "metric.net_sales",
            "context": {
                "word": "sales",
                "proposed": "metric.net_sales",
                "alternatives": ["metric.gross_sales"],
                "safe": "metric.net_sales",
            },
            "fingerprint": "seed",
            "sources": [
                {
                    "type": "ai",
                    "text": "seed",
                    "at": None,
                    "quote": None,
                    "sql": None,
                    "document": None,
                    "section_id": None,
                    "location": None,
                }
            ],
        },
        options=[
            {
                "id": "a",
                "label": "Net sales",
                "explanation": "Completed orders.",
                "number": "359",
                "proposal": {"default": "default.sales", "value": "metric.net_sales"},
            },
            {
                "id": "b",
                "label": "Gross sales",
                "explanation": "Everything before refunds.",
                "number": "459",
                "proposal": {"default": "default.sales", "value": "metric.gross_sales"},
            },
        ],
        default_option="a",
        affects=["metric.net_sales"],
        source="learning",
    )
    db_session.add(row)
    db_session.commit()
    return row.id


def test_idempotent(db_session, version_id, practice_shop, practice_source, learner_client) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)
    log_in(learner_client)
    first = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "a"})
    assert first.status_code == 200, first.text
    again = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "a"})
    assert again.status_code == 200, again.text
    row = db_session.get(OwnerQuestion, question_id)
    assert row.status == "answered"
    assert row.answer["option_id"] == "a"
    assert row.answer["previous"] is None
    entry = store.get_entry(db_session, version_id, "default.sales")
    assert entry.confidence == "confirmed"
    assert entry.details["value"] == "metric.net_sales"
    assert row.answer["retested"] == {"metric.gross_sales": True, "metric.net_sales": True}


def test_unknown_option(db_session, version_id, learner_client) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)
    log_in(learner_client)
    missing = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "z"})
    assert missing.status_code == 400
    both = learner_client.post(
        f"/api/questions/{question_id}/answer", json={"option_id": "a", "text": "hi"}
    )
    assert both.status_code == 400
    empty = learner_client.post(f"/api/questions/{question_id}/answer", json={"text": "  "})
    assert empty.status_code == 400
    gone = learner_client.post("/api/questions/999999/answer", json={"option_id": "a"})
    assert gone.status_code == 404
    row = db_session.get(OwnerQuestion, question_id)
    assert row.status == "waiting"


def test_free_text_pending(db_session, version_id, learner_client) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)
    log_in(learner_client)
    response = learner_client.post(
        f"/api/questions/{question_id}/answer",
        json={"text": "Sales means everything including tax"},
    )
    assert response.status_code == 200, response.text
    row = db_session.get(OwnerQuestion, question_id)
    assert row.status == "answered"
    assert row.answer["text"] == "Sales means everything including tax"
    todos = db_session.scalars(select(LearnerTodo)).all()
    assert len(todos) == 1
    assert todos[0].kind == "correction"
    assert todos[0].status == "open"
    assert todos[0].details["question_id"] == question_id
    entry = store.get_entry(db_session, version_id, "default.sales")
    assert entry.confidence == "guessed"
    assert entry.details["value"] == "metric.net_sales"


def test_skip_default(db_session, version_id, learner_client) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)
    log_in(learner_client)
    response = learner_client.post(f"/api/questions/{question_id}/skip")
    assert response.status_code == 200, response.text
    again = learner_client.post(f"/api/questions/{question_id}/skip")
    assert again.status_code == 200, again.text
    row = db_session.get(OwnerQuestion, question_id)
    assert row.status == "skipped"
    entry = store.get_entry(db_session, version_id, "default.sales")
    assert entry.confidence == "guessed"
    waiting = learner_client.get("/api/questions?status=waiting")
    assert waiting.status_code == 200
    assert waiting.json() == {"questions": []}
    skipped = learner_client.get("/api/questions?status=skipped")
    assert skipped.status_code == 200
    (shown,) = skipped.json()["questions"]
    assert shown["defaultOption"] == "a"
    assert "without marking it confirmed" in shown["defaultReason"]
    assert shown["evidence"]["summary"]
    assert "password" not in str(shown["evidence"]).lower()
    bad = learner_client.get("/api/questions?status=bogus")
    assert bad.status_code == 400


def test_retest_failure(
    db_session, version_id, practice_shop, practice_source, learner_client
) -> None:
    from charie.shared.tables.sources import DocFact, Document, DocumentSection

    _seed_metrics(db_session, version_id)
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
    question_id = _ask_row(db_session)
    log_in(learner_client)
    response = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "a"})
    assert response.status_code == 200, response.text
    row = db_session.get(OwnerQuestion, question_id)
    assert row.answer["retested"] == {"metric.gross_sales": True, "metric.net_sales": False}
    entry = store.get_entry(db_session, version_id, "default.sales")
    assert entry.confidence == "confirmed"
    metric = store.get_entry(db_session, version_id, "metric.net_sales")
    assert metric.confidence == "guessed"
    failed = [check for check in metric.details["tests"] if check.get("passed") is False]
    assert failed and failed[0]["name"] == "matches_documents"


def test_concurrent_answer(db_session, version_id, practice_shop) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)

    def answer(option: str) -> str:
        with session_scope() as session:
            try:
                apply_answer(
                    session, question_id, {"option_id": option}, practice_shop, "America/Chicago"
                )
                session.commit()
            except AnswerConflict:
                session.rollback()
                return "conflict"
            return "saved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(answer, ("a", "b")))
    assert sorted((first, second)) == ["conflict", "saved"]
    with session_scope() as session:
        row = session.get(OwnerQuestion, question_id)
        assert row.status == "answered"
        assert row.answer["option_id"] in ("a", "b")


def _ask_conflict_row(db_session, entry_key: str = "metric.net_sales") -> int:
    row = OwnerQuestion(
        status="waiting",
        rank=1,
        importance=1,
        topic="Which evidence about Net sales is right",
        title="Which evidence about Net sales is right?",
        body="Two pieces of evidence disagree about Net sales.",
        evidence={
            "origin": "conflict",
            "entry_key": entry_key,
            "metric_key": "",
            "context": {"title": "Net sales"},
            "fingerprint": "seed-conflict",
            "sources": [],
        },
        options=[
            {
                "id": "a",
                "label": "The monthly report",
                "explanation": "The report states this number.",
                "proposal": {"entry": entry_key},
            },
            {
                "id": "b",
                "label": "The owner notes",
                "explanation": "The notes state this number.",
                "proposal": {"entry": entry_key},
            },
        ],
        default_option="a",
        affects=[entry_key],
        source="learning",
    )
    db_session.add(row)
    db_session.commit()
    return row.id


def test_change_answer_with_previous(
    db_session, version_id, practice_shop, practice_source, learner_client
) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)
    log_in(learner_client)
    first = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "a"})
    assert first.status_code == 200, first.text
    change = learner_client.post(
        f"/api/questions/{question_id}/answer",
        json={"option_id": "b", "previous_option_id": "a"},
    )
    assert change.status_code == 200, change.text
    row = db_session.get(OwnerQuestion, question_id)
    assert row.status == "answered"
    assert row.answer["option_id"] == "b"
    assert row.answer["previous"] == {"option_id": "a"}
    entry = store.get_entry(db_session, version_id, "default.sales")
    assert entry.confidence == "confirmed"
    assert entry.details["value"] == "metric.gross_sales"


def test_change_answer_without_previous_conflicts(
    db_session, version_id, practice_shop, practice_source, learner_client
) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)
    log_in(learner_client)
    first = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "a"})
    assert first.status_code == 200, first.text
    change = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "b"})
    assert change.status_code == 409
    row = db_session.get(OwnerQuestion, question_id)
    assert row.answer["option_id"] == "a"
    entry = store.get_entry(db_session, version_id, "default.sales")
    assert entry.details["value"] == "metric.net_sales"


def test_change_answer_stale_previous_conflicts(
    db_session, version_id, practice_shop, practice_source, learner_client
) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)
    log_in(learner_client)
    assert (
        learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "a"})
    ).status_code == 200
    changed = learner_client.post(
        f"/api/questions/{question_id}/answer",
        json={"option_id": "b", "previous_option_id": "a"},
    )
    assert changed.status_code == 200, changed.text
    stale = learner_client.post(
        f"/api/questions/{question_id}/answer",
        json={"option_id": "a", "previous_option_id": "a"},
    )
    assert stale.status_code == 409
    row = db_session.get(OwnerQuestion, question_id)
    assert row.answer["option_id"] == "b"


def test_change_text_with_previous(
    db_session, version_id, practice_shop, practice_source, learner_client
) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_row(db_session)
    log_in(learner_client)
    first = learner_client.post(
        f"/api/questions/{question_id}/answer", json={"text": "Sales means net"}
    )
    assert first.status_code == 200, first.text
    change = learner_client.post(
        f"/api/questions/{question_id}/answer",
        json={"text": "Sales means gross", "previous_text": "Sales means net"},
    )
    assert change.status_code == 200, change.text
    row = db_session.get(OwnerQuestion, question_id)
    assert row.answer["text"] == "Sales means gross"
    assert row.answer["previous"] == {"text": "Sales means net"}


def test_conflict_choice_resolves_entry(
    db_session, version_id, practice_shop, practice_source, learner_client
) -> None:
    _seed_metrics(db_session, version_id)
    current = store.get_entry(db_session, version_id, "metric.net_sales")
    store.upsert_entry(
        db_session,
        version_id,
        "metric.net_sales",
        "metric",
        current.title,
        current.meaning,
        dict(current.details),
        "conflicting",
        list(current.sources),
        "Two documents disagree.",
    )
    db_session.commit()
    question_id = _ask_conflict_row(db_session)
    log_in(learner_client)
    response = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "a"})
    assert response.status_code == 200, response.text
    row = db_session.get(OwnerQuestion, question_id)
    assert row.status == "answered"
    assert row.answer["applied"] == [
        {"entry": "metric.net_sales", "before": "conflicting", "after": "confirmed"}
    ]
    assert row.answer["retested"] == {"metric.gross_sales": True, "metric.net_sales": True}
    entry = store.get_entry(db_session, version_id, "metric.net_sales")
    assert entry.confidence == "confirmed"
    assert any(source.get("type") == "owner_answer" for source in entry.sources or [])


def test_conflict_choice_rejected_when_not_conflicting(
    db_session, version_id, practice_shop, practice_source, learner_client
) -> None:
    _seed_metrics(db_session, version_id)
    question_id = _ask_conflict_row(db_session)
    log_in(learner_client)
    response = learner_client.post(f"/api/questions/{question_id}/answer", json={"option_id": "a"})
    assert response.status_code == 400
    row = db_session.get(OwnerQuestion, question_id)
    assert row.status == "waiting"
    entry = store.get_entry(db_session, version_id, "metric.net_sales")
    assert entry.confidence == "checked"
    assert not any(source.get("type") == "owner_answer" for source in entry.sources or [])


def test_conflict_choice_rejected_outside_scope(
    db_session, version_id, practice_shop, practice_source, learner_client
) -> None:
    _seed_metrics(db_session, version_id)
    row = OwnerQuestion(
        status="waiting",
        rank=1,
        importance=1,
        topic="Which evidence about Net sales is right",
        title="Which evidence about Net sales is right?",
        body="Two pieces of evidence disagree about Net sales.",
        evidence={
            "origin": "conflict",
            "entry_key": "metric.net_sales",
            "metric_key": "",
            "context": {"title": "Net sales"},
            "fingerprint": "seed-scope",
            "sources": [],
        },
        options=[
            {
                "id": "a",
                "label": "Gross sales instead",
                "explanation": "A different entry entirely.",
                "proposal": {"entry": "metric.gross_sales"},
            },
        ],
        default_option="a",
        affects=["metric.net_sales"],
        source="learning",
    )
    db_session.add(row)
    db_session.commit()
    log_in(learner_client)
    response = learner_client.post(f"/api/questions/{row.id}/answer", json={"option_id": "a"})
    assert response.status_code == 400
    assert db_session.get(OwnerQuestion, row.id).status == "waiting"
