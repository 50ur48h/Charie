"""Retries: busy APIs wait and retry; other 4xx fail at once."""

import pytest
from pydantic import BaseModel, Field

from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiApiError, AiOutOfCredit, AiUnavailable
from charie.shared.ai.provider import AiCallError


class Title(BaseModel):
    title: str = Field(description="A short title.")


def _client(provider, prompts_dir, sleeps):
    return AiClient(
        provider=provider,
        prompts_dir=prompts_dir,
        sleep=sleeps.append,
        cost_log=MemoryCostLog(),
    )


def _run(client):
    return client.run("name_chat", {"topic": "sales"}, Title, app="tests")


def test_429_waits_for_retry_after(provider, prompts_dir):
    sleeps: list = []
    provider.fail(AiCallError(status=429, message="busy", retry_after=5.0)).reply(
        '{"title": "Sales up"}'
    )
    result = _run(_client(provider, prompts_dir, sleeps))
    assert result.title == "Sales up"
    assert len(sleeps) == 1
    assert 5.0 <= sleeps[0] <= 6.0


def test_waits_double_with_randomness(provider, prompts_dir):
    sleeps: list = []
    for _ in range(3):
        provider.fail(AiCallError(status=429, message="busy"))
    provider.reply('{"title": "Sales up"}')
    assert _run(_client(provider, prompts_dir, sleeps)).title == "Sales up"
    assert 1.0 <= sleeps[0] <= 2.0
    assert 2.0 <= sleeps[1] <= 3.0
    assert 4.0 <= sleeps[2] <= 5.0


def test_5xx_timeout_and_connection_retried(provider, prompts_dir):
    sleeps: list = []
    provider.fail(AiCallError(status=503, message="down")).fail(
        AiCallError(status=None, code="timeout", message="slow")
    ).fail(AiCallError(status=None, code="connection", message="lost"))
    provider.reply('{"title": "Sales up"}')
    assert _run(_client(provider, prompts_dir, sleeps)).title == "Sales up"
    assert len(sleeps) == 3


def test_gives_up_after_five_retries(provider, prompts_dir):
    sleeps: list = []
    for _ in range(10):
        provider.fail(AiCallError(status=429, message="busy"))
    with pytest.raises(AiUnavailable, match="after 5 tries"):
        _run(_client(provider, prompts_dir, sleeps))
    assert len(provider.calls) == 6
    assert len(sleeps) == 5


def test_400_not_retried(provider, prompts_dir):
    sleeps: list = []
    provider.fail(AiCallError(status=400, message="bad request\nsecond line"))
    with pytest.raises(AiApiError, match="bad request"):
        _run(_client(provider, prompts_dir, sleeps))
    assert len(provider.calls) == 1
    assert sleeps == []


def test_out_of_credit_not_retried(provider, prompts_dir):
    sleeps: list = []
    provider.fail(AiCallError(status=402, message="billing issue"))
    with pytest.raises(AiOutOfCredit, match="out of credit"):
        _run(_client(provider, prompts_dir, sleeps))
    assert len(provider.calls) == 1
