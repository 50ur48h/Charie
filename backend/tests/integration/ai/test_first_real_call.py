"""The first real call (laptop only: `pytest -m live_ai ...`). Costs money."""

import pytest
from sqlalchemy import select

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import get_ai
from charie.shared.ai.prices import call_cost
from charie.shared.db import session_scope
from charie.shared.tables.usage import AiCall


@pytest.mark.live_ai
def test_name_chat_real_call(db) -> None:
    result = get_ai().run("name_chat", {"topic": "test sales question"}, ChatTitle, app="tests")
    assert isinstance(result, ChatTitle) and result.title
    with session_scope() as session:
        row = session.scalar(
            select(AiCall)
            .where(AiCall.job == "name_chat", AiCall.app == "tests")
            .order_by(AiCall.id.desc())
        )
    assert row is not None and row.status == "ok"
    assert row.prompt_tokens > 0 and row.completion_tokens > 0
    assert row.cost_usd == call_cost(
        row.model, row.prompt_tokens, row.cached_tokens, row.completion_tokens
    )
    assert 0 < row.cost_usd < 0.01
