"""Fake AI: queued replies and failures, no network."""

import pytest

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiApiError
from charie.shared.ai.fake import FakeAi


def _client(fake: FakeAi, prompts_dir) -> AiClient:
    return AiClient(
        provider=fake, prompts_dir=prompts_dir, sleep=lambda s: None, cost_log=MemoryCostLog()
    )


def test_queued_reply(prompts_dir) -> None:
    fake = FakeAi()
    fake.reply("name_chat", {"title": "Hello"})
    result = _client(fake, prompts_dir).run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")
    assert result.title == "Hello"


def test_queued_error(prompts_dir) -> None:
    fake = FakeAi()
    fake.fail("name_chat", AiApiError("boom"))
    with pytest.raises(AiApiError):
        _client(fake, prompts_dir).run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")


def test_calls_recorded(prompts_dir) -> None:
    fake = FakeAi()
    fake.reply("name_chat", ChatTitle(title="Hello"))
    _client(fake, prompts_dir).run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")
    assert len(fake.calls) == 1
    job, messages = fake.calls[0]
    assert job == "name_chat" and messages


def test_nothing_queued_message(prompts_dir) -> None:
    with pytest.raises(Exception, match="no reply queued for job `name_chat`"):
        _client(FakeAi(), prompts_dir).run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")
