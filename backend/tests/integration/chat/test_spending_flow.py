"""Spend 5 cents of test AI calls, then compare the real totals (P12.2)."""

import time
from decimal import Decimal

from charie.shared.tables.usage import AiCall
from tests.conftest import log_in


def _test_call(db_session, cost: str) -> None:
    db_session.add(
        AiCall(
            app="tests",
            job="write_answer",
            provider="meta",
            model="muse-wonder-1.0",
            cost_usd=Decimal(cost),
        )
    )
    db_session.commit()


def test_five_cents_matches_real_totals(chat_client, db_session) -> None:
    """5 cents of test calls show as 5 cents on status and usage."""
    log_in(chat_client)
    _test_call(db_session, "0.02")
    _test_call(db_session, "0.03")
    time.sleep(5)
    status = chat_client.get("/api/status")
    assert status.status_code == 200, status.text
    assert status.json()["spending"]["spent_usd"] == 0.05
    usage = chat_client.get("/api/usage")
    assert usage.status_code == 200, usage.text
    assert usage.json()["spent_usd"] == 0.05
