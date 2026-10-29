"""The cost log writes real `ai_calls` rows (throwaway database)."""

from datetime import UTC, datetime

from sqlalchemy import select

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import DbCostLog
from charie.shared.ai.fake import FakeAi
from charie.shared.ai.prices import call_cost
from charie.shared.db import session_scope
from charie.shared.tables.usage import AiCall

JOB = "name_chat"


def test_row_saved_in_ai_calls(db) -> None:
    fake = FakeAi()
    fake.reply(JOB, {"title": "Hello"})
    AiClient(provider=fake, sleep=lambda s: None).run(JOB, {"topic": "hi"}, ChatTitle, app="chat")
    with session_scope() as session:
        row = session.scalar(select(AiCall).where(AiCall.job == JOB))
        assert row is not None
        status = row.status
        tokens = (row.prompt_tokens, row.cached_tokens, row.completion_tokens)
        cost = row.cost_usd
    assert status == "ok"
    assert tokens == (100, 0, 20)
    assert cost == call_cost("muse-wonder-1.0", 100, 0, 20)


def test_month_spent_from_database(db) -> None:
    log = DbCostLog()
    assert log.month_spent(datetime.now(UTC)) == 0
    fake = FakeAi()
    fake.reply(JOB, {"title": "Hello"})
    AiClient(provider=fake, sleep=lambda s: None, cost_log=log).run(
        JOB, {"topic": "hi"}, ChatTitle, app="chat"
    )
    assert log.month_spent(datetime.now(UTC)) == call_cost("muse-wonder-1.0", 100, 0, 20)
