"""Fixtures for the analyst's chat tests (P10.4).

Every test that asks a question must wait for the background answer to
finish (poll for done) before returning. Otherwise teardown closes the
test client while the analyst still holds a database transaction, and
the next truncate waits on its lock forever.
"""

import os
from datetime import UTC, datetime
from urllib.parse import urlparse

import pytest

from charie.chat.chat_store import build_context
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.sources import DataSource
from tests.integration.chat import snapshot as snapshot_module


@pytest.fixture()
def kb_version(db_session) -> int:
    """The frozen knowledge, loaded fresh for each test."""
    return snapshot_module.load_snapshot(db_session)


@pytest.fixture()
def practice_source(db_session) -> DataSource:
    """A `data_sources` row from PRACTICE_DB_URL; never connected here."""
    raw = os.environ.get("PRACTICE_DB_URL", "postgresql://localhost:5432/shop")
    target = urlparse(raw if "://" in raw else f"postgresql://{raw}")
    row = DataSource(
        kind="postgres",
        name="Practice database",
        host=target.hostname or "localhost",
        port=target.port or 5432,
        database=(target.path or "/shop").lstrip("/"),
        username=target.username or "owner",
        password_encrypted="not-encrypted-in-test",
        status="connected",
        data_through=datetime(2025, 12, 31, tzinfo=UTC),
    )
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture()
def analyst_ctx(db_session, kb_version):
    """A chat with one question, as the runner would build it."""
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    user_message = Message(
        chat_id=chat.id,
        role="user",
        text_="Net sales in December 2025",
        status="done",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    assistant = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status="thinking",
        mode="thinking",
        kb_version_id=kb_version,
        started_at=datetime.now(UTC),
    )
    db_session.add(user_message)
    db_session.add(assistant)
    db_session.commit()
    return build_context(assistant.id)


def _understanding_reply(**overrides) -> dict:
    """A good `understand_question` reply, with overrides."""
    reply = {
        "kind": "clear",
        "reading": "I read this as **net sales** for [p1].",
        "periods": [{"kind": "month", "number": 12}],
        "asks": [],
        "filters": [],
        "defaults_used": [],
        "document_topics": [],
    }
    reply.update(overrides)
    return reply


def fake_understanding(monkeypatch, *replies: dict) -> FakeAi:
    """Point `understand` at queued FakeAi replies (no network)."""
    from charie.chat.analyst import understand as understand_module

    fake = FakeAi()
    for reply in replies or (_understanding_reply(),):
        fake.reply("understand_question", reply)
    monkeypatch.setattr(
        understand_module,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    return fake
