"""Owner questions: checked option numbers and honest failures (P09.5, fake AI)."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, text

from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.knowledge import questions, store, versions
from charie.shared.knowledge.questions import FAILED_NUMBER_TEXT, gather_topics
from charie.shared.tables.questions import OwnerQuestion


@pytest.fixture()
def practice_shop(db):
    """The practice shop schema with a stub connector for option numbers."""
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


@pytest.fixture()
def version_id(db_session):
    return versions.get_or_create_draft(db_session, "first_learning").id


def _seed(db_session, version_id: int) -> None:
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


def _ask(db_session, version_id, monkeypatch, reply, run):
    fake = FakeAi().reply("write_owner_questions", reply)
    client = AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None)
    monkeypatch.setattr(questions, "get_ai", lambda: client)
    topics = gather_topics(db_session, version_id)
    assert [topic.topic for topic in topics] == ["What “sales” means"]
    return questions.make_owner_questions(db_session, version_id, topics, run, "America/Chicago")


def _question(db_session, topic: str) -> OwnerQuestion:
    rows = db_session.scalars(select(OwnerQuestion).where(OwnerQuestion.topic == topic)).all()
    assert len(rows) == 1
    return rows[0]


def test_option_numbers_checked(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed(db_session, version_id)
    created, pending = _ask(
        db_session,
        version_id,
        monkeypatch,
        {
            "questions": [
                {
                    "topic": "What “sales” means",
                    "title": "What should sales mean?",
                    "body": "This decides which number sales questions use.",
                    "options": [
                        {
                            "id": "a",
                            "label": "Net sales",
                            "explanation": "Completed orders without delivery fees.",
                            "proposal": {"metric": "metric.net_sales"},
                        },
                        {
                            "id": "b",
                            "label": "Gross sales",
                            "explanation": "Everything before refunds.",
                            "proposal": {"metric": "metric.gross_sales"},
                        },
                    ],
                    "default_option": "a",
                }
            ]
        },
        lambda sql: practice_shop.run_query(sql).rows,
    )
    assert len(created) == 1
    assert pending == []
    row = _question(db_session, "What “sales” means")
    assert row.status == "waiting"
    assert row.default_option == "a"
    assert row.options == [
        {
            "id": "a",
            "label": "Net sales",
            "explanation": "Completed orders without delivery fees.",
            "number": "359",
            "proposal": {"metric": "metric.net_sales"},
        },
        {
            "id": "b",
            "label": "Gross sales",
            "explanation": "Everything before refunds.",
            "number": "459",
            "proposal": {"metric": "metric.gross_sales"},
        },
    ]


def test_failed_option_honest(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed(db_session, version_id)
    created, _ = _ask(
        db_session,
        version_id,
        monkeypatch,
        {
            "questions": [
                {
                    "topic": "What “sales” means",
                    "title": "What should sales mean?",
                    "body": "This decides which number sales questions use.",
                    "options": [
                        {
                            "id": "a",
                            "label": "Net sales",
                            "explanation": "Completed orders.",
                            "proposal": {"metric": "metric.net_sales"},
                        },
                        {
                            "id": "b",
                            "label": "Something else",
                            "explanation": "Not learned yet.",
                            "proposal": {"metric": "metric.missing"},
                        },
                    ],
                    "default_option": "a",
                }
            ]
        },
        lambda sql: practice_shop.run_query(sql).rows,
    )
    assert len(created) == 1
    row = _question(db_session, "What “sales” means")
    numbers = {option["id"]: option["number"] for option in row.options}
    assert numbers == {"a": "359", "b": FAILED_NUMBER_TEXT}


def test_sources_and_defaults(db_session, version_id, practice_shop, monkeypatch) -> None:
    _seed(db_session, version_id)
    created, _ = _ask(
        db_session,
        version_id,
        monkeypatch,
        {
            "questions": [
                {
                    "topic": "What “sales” means",
                    "title": "What should sales mean?",
                    "body": "This decides which number sales questions use.",
                    "options": [
                        {
                            "id": "a",
                            "label": "Net sales",
                            "explanation": "Completed orders.",
                            "proposal": {"default": "default.sales", "value": "metric.net_sales"},
                        },
                        {
                            "id": "b",
                            "label": "Gross sales",
                            "explanation": "Everything before refunds.",
                            "proposal": {"default": "default.sales", "value": "metric.gross_sales"},
                        },
                    ],
                    "default_option": "a",
                }
            ]
        },
        lambda sql: practice_shop.run_query(sql).rows,
    )
    assert len(created) == 1
    row = _question(db_session, "What “sales” means")
    assert row.evidence["origin"] == "default"
    assert row.evidence["entry_key"] == "default.sales"
    assert row.evidence["fingerprint"]
    assert [(source["type"], source["text"]) for source in row.evidence["sources"]] == [
        ("ai", "seed")
    ]
    assert row.affects == ["metric.net_sales"]
    assert row.importance == 1
    assert row.rank == 1
    numbers = {option["id"]: option["number"] for option in row.options}
    assert numbers == {"a": "359", "b": "459"}
