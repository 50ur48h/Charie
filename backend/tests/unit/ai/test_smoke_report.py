"""The smoke report copies row values while the session is still open."""

from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from charie.shared.ai.smoke import latest_report
from charie.shared.db import Base


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.tables["ai_calls"].create(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ai_calls (id, at, app, job, provider, model,"
                " prompt_tokens, cached_tokens, completion_tokens, reasoning_tokens,"
                " cost_usd, duration_ms, status)"
                " VALUES (1, '2026-10-01 00:00:00', 'tests', 'name_chat', 'meta',"
                " 'muse-wonder-1.0', 100, 10, 20, 5, 0.0008, 12, 'ok')"
            )
        )
    return Session(engine)


def test_report_survives_session_close() -> None:
    session = _session()
    report = latest_report(session, "name_chat", "tests")
    session.close()
    assert report is not None
    assert report["prompt_tokens"] == 100 and report["cached_tokens"] == 10
    assert report["completion_tokens"] == 20 and report["reasoning_tokens"] == 5
    assert report["cost_usd"] == Decimal("0.0008")


def test_report_missing_row_is_none() -> None:
    session = _session()
    try:
        assert latest_report(session, "nope", "tests") is None
    finally:
        session.close()
