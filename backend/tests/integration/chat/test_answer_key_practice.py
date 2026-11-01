"""The data helper on the practice questions and database (P10.6 Task 5).

Laptop-only: needs the practice database and a live AI call. Mark
`practice_db` and `live_ai`; replays stay off so it always calls Meta.
Recording costs under $0.50; replaying is impossible by design.
"""

import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlparse

import pytest

from charie.chat.analyst.notebook import Notebook
from charie.shared.crypto import encrypt_text
from charie.shared.settings import set_setting
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.sources import DataSource
from tests.conftest import log_in

#: clear-001's checked net sales for December 2025, tolerance 1.
NET_SALES_VALUE = "1354004.6300"


def _seed_net_sales(db_session) -> None:
    """A published `net_sales` recipe mirroring clear-001's checked SQL."""
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="net_sales",
            kind="metric",
            title="Net sales",
            meaning="Order totals minus tax and delivery fees.",
            details={
                "kind": "simple",
                "title": "Net sales",
                "table": "public.orders",
                "aggregate": "sum",
                "expression": "orders.total_amount - orders.tax_amount - orders.delivery_fee",
                "filters": [],
                "time_column": "public.orders.created_at",
                "time_column_type": "timestamptz",
                "dimensions": [],
                "unit": "money",
                "currency": "USD",
                "steps_in_words": ["Add up order amounts.", "Take off tax and fees."],
                "tests": [{"name": "runs", "passed": True}],
            },
            confidence="checked",
            sources=[],
        )
    )
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="public.orders",
            kind="table",
            title="public.orders",
            meaning="Shop orders.",
            details={"schema": "public", "name": "orders"},
            confidence="checked",
            sources=[],
        )
    )
    raw = os.environ["PRACTICE_DB_URL"]
    target = urlparse(raw if "://" in raw else f"postgresql://{raw}")
    db_session.add(
        DataSource(
            kind="postgres",
            name="Practice database",
            host=target.hostname or "localhost",
            port=target.port or 5432,
            database=(target.path or "/shop").lstrip("/"),
            username=target.username or "owner",
            password_encrypted=encrypt_text(target.password or ""),
            status="connected",
            data_through=datetime(2025, 12, 31, tzinfo=UTC),
        )
    )
    set_setting(db_session, "time_zone", "America/Chicago")
    db_session.commit()


@pytest.mark.practice_db
@pytest.mark.live_ai
def test_answer_key_practice(chat_client, db_session, monkeypatch) -> None:
    """Net sales in December 2025 matches clear-001's checked number."""
    monkeypatch.setenv("AI_REPLAY", "off")
    _seed_net_sales(db_session)
    log_in(chat_client)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    assistant_id = chat_client.post(
        f"/api/chats/{chat_id}/messages", json={"text": "Net sales in December 2025"}
    ).json()["assistant_message_id"]
    assistant = {}
    for _ in range(200):
        opened = chat_client.get(f"/api/chats/{chat_id}").json()
        assistant = next(item for item in opened["messages"] if item["id"] == assistant_id)
        if assistant["status"] == "done":
            break
        time.sleep(1.0)
    assert assistant["status"] == "done", assistant
    book = Notebook.load(db_session, assistant_id, chat_id)
    numbers = [item for item in book.items() if item.kind == "number"]
    assert numbers, "the notebook has no numbers"
    assert abs(Decimal(numbers[0].value["value"]) - Decimal(NET_SALES_VALUE)) <= 1
