"""A real correction after the past changes (P11.4).

Fake AI throughout; no paid calls. The chat already said net sales
were $355.00 on data through 2025-12-31; the new answer uses data
through 2026-01-31 and says $360.00. The answer must explain the
change with the data_updated note and pass every check. The
practice-database replay with a genuine data update stays in Task 5,
which needs fresh paid recordings (owner yes + cost prompt still
required).
"""

import asyncio
import json
from datetime import UTC, datetime

from charie.chat.analyst.answer import answer_question
from charie.chat.analyst.chat_context import ChatContext, SaidFact, save_context
from charie.chat.analyst.notebook import Notebook, NumberValue
from charie.chat.chat_store import build_context
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.knowledge import KbEntry, KbVersion
from tests.integration.chat.conftest import fake_understanding


def _seed(db_session):
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
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    fact = {
        "metric": "metric.net_sales",
        "filters": [],
        "split": {},
        "period": "2026-01-01/2026-01-31",
        "compare_period": "",
        "measure": "value",
    }
    save_context(
        db_session,
        chat.id,
        ChatContext(
            said=[
                SaidFact(
                    ref="n1",
                    key=json.dumps(fact),
                    description="Net sales",
                    text="$355.00",
                    value="355.00",
                    unit="money",
                    currency="USD",
                    data_through="2025-12-31",
                    kb_version=version.id,
                    message_id=7,
                )
            ]
        ),
    )
    user_message = Message(
        chat_id=chat.id,
        role="user",
        text_="What were net sales in January 2026?",
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
        data_through=datetime(2026, 1, 31),
        started_at=datetime.now(UTC),
    )
    db_session.add(user_message)
    db_session.add(assistant)
    db_session.commit()
    book = Notebook(db_session, assistant.id, chat.id)
    book.add_number(
        "Net sales",
        NumberValue(value="360.00", unit="money"),
        {"fact_key": fact},
    )
    db_session.commit()
    return build_context(assistant.id)


def _write_reply():
    return {
        "blocks": [
            {
                "type": "text",
                "sentences": [
                    {
                        "kind": "fact",
                        "text": "Net sales were [n1].",
                        "proof": ["n1"],
                        "starts_paragraph": True,
                    }
                ],
            }
        ]
    }


def _patch(monkeypatch, module, job, replies) -> FakeAi:
    fake = FakeAi()
    for reply in replies:
        fake.reply(job, reply)
    monkeypatch.setattr(
        module,
        "get_ai",
        lambda: AiClient(provider=fake, cost_log=MemoryCostLog(), sleep=lambda s: None),
    )
    return fake


def test_correction_after_a_data_update_is_explained(db_session, monkeypatch) -> None:
    """The data_updated note joins the answer, and every check passes."""
    from charie.chat.analyst import enough as enough_module
    from charie.chat.analyst import review as review_module
    from charie.chat.analyst import write as write_module

    ctx = _seed(db_session)
    fake_understanding(
        monkeypatch,
        {
            "kind": "clear",
            "reading": "I read this as net sales for [p1].",
            "periods": [{"kind": "month", "number": 1, "year": 2026}],
            "asks": [],
            "filters": [],
            "defaults_used": [],
            "document_topics": [],
        },
    )
    _patch(monkeypatch, enough_module, "check_enough", [{"enough": True, "missing": ""}])
    _patch(
        monkeypatch,
        review_module,
        "review_answer",
        [{"verdict": "good", "fixes": [], "needs_more_data": False, "missing_data": ""}],
    )
    _patch(monkeypatch, write_module, "write_answer", [_write_reply()])
    asyncio.run(answer_question(ctx))
    message = db_session.get(Message, ctx.message_id)
    assert message.status == "done"
    callouts = [block for block in message.answer["blocks"] if block.get("type") == "callout"]
    assert callouts == [
        {
            "type": "callout",
            "tone": "note",
            "text": "Correction: earlier in this chat I said Net sales was $355.00. "
            "It's now $360.00, because more data has come in (it now goes up to 31 Jan 2026).",
        }
    ]
