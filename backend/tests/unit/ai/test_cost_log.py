"""Cost log: one row per status, retried rows, zero-cost failures."""

import pytest

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiUnavailable
from charie.shared.ai.prices import call_cost
from charie.shared.ai.provider import AiCallError


def _client(provider, prompts_dir, log: MemoryCostLog) -> AiClient:
    return AiClient(provider=provider, prompts_dir=prompts_dir, sleep=lambda s: None, cost_log=log)


def test_reply_logged_with_tokens_and_cost(provider, prompts_dir) -> None:
    log = MemoryCostLog()
    provider.reply('{"title": "Hi"}', prompt_tokens=100, cached_tokens=10, completion_tokens=20)
    _client(provider, prompts_dir, log).run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")
    assert len(log.rows) == 1
    row = log.rows[0]
    assert row["status"] == "ok" and row["prompt_tokens"] == 100
    assert row["cost_usd"] == call_cost("muse-wonder-1.0", 100, 10, 20)
    assert row["app"] == "chat" and row["error"] is None


def test_retried_then_ok_rows(provider, prompts_dir) -> None:
    log = MemoryCostLog()
    provider.reply("not json", prompt_tokens=50, completion_tokens=5)
    provider.reply('{"title": "Hi"}', prompt_tokens=60, completion_tokens=6)
    _client(provider, prompts_dir, log).run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")
    assert [row["status"] for row in log.rows] == ["retried", "ok"]
    assert log.rows[0]["error"] is None
    assert log.rows[0]["cost_usd"] == call_cost("muse-wonder-1.0", 50, 0, 5)


def test_failed_without_reply_costs_zero(provider, prompts_dir) -> None:
    for _ in range(6):
        provider.fail(AiCallError(status=429, code="limited", message="nope"))
    log = MemoryCostLog()
    with pytest.raises(AiUnavailable):
        _client(provider, prompts_dir, log).run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")
    assert len(log.rows) == 1
    row = log.rows[0]
    assert row["status"] == "failed" and row["prompt_tokens"] == 0
    assert row["cost_usd"] == 0 and row["error"] == AiUnavailable().message
