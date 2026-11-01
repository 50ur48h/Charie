"""How did we do in December 2025, on the practice database (P10.10 Task 4).

Laptop-only: needs the practice database and the recorded AI replies.
Recording costs about $1-3: run `AI_REPLAY=record uv run pytest <this file>`
once with the owner's yes, then replay. Without cassettes it fails by
design, like the understand replays.
"""

import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest

from charie.chat.analyst.notebook import Notebook
from charie.shared.crypto import encrypt_text
from charie.shared.settings import set_setting
from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.sources import DataSource
from tests.conftest import log_in
from tests.questions.format import load_questions

PUBLIC = Path(__file__).resolve().parents[2] / "questions" / "public.yaml"

ALLOWED_TYPES = {
    "reading",
    "text",
    "kpis",
    "chart",
    "table",
    "tree",
    "callout",
    "suggestions",
    "method",
    "follow_ups",
}


def _seed_december(db_session) -> None:
    """The three December recipes, mirroring vague-001's answer key SQL."""
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()

    def _entry(key, kind, details, title):
        db_session.add(
            KbEntry(
                version_id=version.id,
                key=key,
                kind=kind,
                title=title,
                meaning=f"{title} meaning",
                details=details,
                confidence="checked",
                sources=[],
            )
        )

    net = {
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
    }
    _entry("net_sales", "metric", net, "Net sales")
    _entry(
        "orders",
        "metric",
        {
            **net,
            "title": "Orders",
            "aggregate": "count",
            "expression": "*",
            "unit": "count",
            "steps_in_words": ["Count every order in the period."],
        },
        "Orders",
    )
    _entry(
        "average_order",
        "metric",
        {
            "kind": "ratio",
            "title": "Average order",
            "numerator": "net_sales",
            "denominator": "orders",
            "dimensions": [],
            "unit": "ratio",
            "steps_in_words": ["Add up order totals and count the orders separately."],
            "tests": [{"name": "runs", "passed": True}],
        },
        "Average order",
    )
    _entry(
        "public.orders",
        "table",
        {"schema": "public", "name": "orders"},
        "public.orders",
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
def test_how_did_we_do_december_2025(chat_client, db_session) -> None:
    """Net sales, orders and average order match vague-001, in 09 blocks only."""
    _seed_december(db_session)
    cases = {case.id: case for case in load_questions(str(PUBLIC), "public")}
    expected = {item.name: item for item in cases["vague-001"].expect.numbers}
    log_in(chat_client)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    assistant_id = chat_client.post(
        f"/api/chats/{chat_id}/messages", json={"text": "How are we doing?"}
    ).json()["assistant_message_id"]
    assistant = {}
    for _ in range(300):
        opened = chat_client.get(f"/api/chats/{chat_id}").json()
        assistant = next(item for item in opened["messages"] if item["id"] == assistant_id)
        if assistant["status"] == "done":
            break
        time.sleep(1.0)
    assert assistant["status"] == "done", assistant
    book = Notebook.load(db_session, assistant_id, chat_id)
    found = {}
    for item in book.items():
        if item.kind == "number":
            found[(item.proof or {}).get("recipe_key", "")] = Decimal(item.value["value"])
    for key in ("net_sales", "orders", "average_order"):
        want = expected[key.replace("_", " ")]
        assert abs(found[key] - want.value) <= want.tolerance, (key, found.get(key), want)
    assert assistant["answer"]["blocks"], "the answer has no blocks"
    for block in assistant["answer"]["blocks"]:
        assert block["type"] in ALLOWED_TYPES, block
