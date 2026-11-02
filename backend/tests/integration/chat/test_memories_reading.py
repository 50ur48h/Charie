"""Saved memories change how vague words read (P11.5).

Fake AI throughout; no paid calls. The live proof that a saved
preference changes a real answer stays in Task 3, which needs fresh
paid recordings (owner yes + cost prompt still required).
"""

from datetime import UTC, datetime

from charie.chat.analyst.understand import understand_input
from charie.chat.chat_store import build_context
from charie.shared.tables.chat import Chat, Memory, Message
from charie.shared.tables.knowledge import KbEntry, KbVersion
from tests.integration.chat.conftest import fake_understanding


def _seed(db_session, memory_on=True):
    from charie.shared.settings import set_setting

    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="metric.net_sales",
            kind="metric",
            title="Net sales",
            meaning="Money kept after refunds.",
            details={},
            confidence="checked",
            sources=[],
        )
    )
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="default.sales",
            kind="default",
            title="sales",
            meaning="net_sales",
            details={"word": "sales", "value": "net_sales", "metrics": ["net_sales"]},
            confidence="checked",
            sources=[],
        )
    )
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    set_setting(db_session, "memory_on", memory_on)
    memory = Memory(
        text_='For me, "sales" means without delivery fees.',
        kind="meaning",
        source_chat_id=chat.id,
        active=True,
    )
    db_session.add(memory)
    user_message = Message(
        chat_id=chat.id,
        role="user",
        text_="What were sales in December 2025?",
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
        kb_version_id=version.id,
        started_at=datetime.now(UTC),
    )
    db_session.add(user_message)
    db_session.add(assistant)
    db_session.commit()
    return build_context(assistant.id), version.id


def test_memories_reach_the_understand_prompt(db_session) -> None:
    """The saved preference rides along when memory is on, and not when off."""
    from charie.chat.analyst.kb_view import KbView

    ctx, version_id = _seed(db_session)
    kb = KbView.load(db_session, version_id)
    inputs = understand_input(ctx, kb)
    assert inputs["memories"] == ['For me, "sales" means without delivery fees.']
    from charie.shared.settings import set_setting

    set_setting(db_session, "memory_on", False)
    db_session.commit()
    assert understand_input(ctx, kb)["memories"] == []


def test_a_saved_meaning_changes_the_reading(db_session, monkeypatch) -> None:
    """The AI follows the saved meaning and says so in the reading."""
    from charie.chat.analyst.understand import understand

    ctx, version_id = _seed(db_session)
    fake_understanding(
        monkeypatch,
        {
            "kind": "vague_with_default",
            "reading": "I read this as sales without delivery fees for [p1].",
            "periods": [{"kind": "month", "number": 12}],
            "asks": [{"metric_key": "metric.net_sales"}],
            "filters": [],
            "defaults_used": ["default.sales"],
            "document_topics": [],
        },
    )
    understand(ctx)
    assert ctx.understanding.defaults_used == ["default.sales"]
    assert "without delivery fees" in ctx.understanding.reading
