"""Repair: one bad reply gets one more chance, then a plain error."""

import pytest
from pydantic import BaseModel, Field

from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiFormError


class Title(BaseModel):
    title: str = Field(description="A short title.")


def _client(provider, prompts_dir):
    return AiClient(
        provider=provider,
        prompts_dir=prompts_dir,
        sleep=lambda s: None,
        cost_log=MemoryCostLog(),
    )


def test_bad_reply_gets_one_repair(provider, prompts_dir):
    provider.reply("not json at all").reply('{"title": "Sales up"}')
    result = _client(provider, prompts_dir).run("name_chat", {"topic": "sales"}, Title, app="tests")
    assert result.title == "Sales up"
    assert len(provider.calls) == 2
    repair_text = provider.calls[1].messages[-1]["content"]
    assert "not json at all" in repair_text
    assert "the reply is not JSON" in repair_text


def test_second_bad_reply_raises_form_error(provider, prompts_dir):
    provider.reply("nope").reply("still nope")
    with pytest.raises(AiFormError, match="didn't match the required form"):
        _client(provider, prompts_dir).run("name_chat", {"topic": "sales"}, Title, app="tests")


def test_repair_message_lists_problems(provider, prompts_dir):
    provider.reply('{"wrong": 1}').reply('{"title": "Sales up"}')
    _client(provider, prompts_dir).run("name_chat", {"topic": "sales"}, Title, app="tests")
    repair_text = provider.calls[1].messages[-1]["content"]
    assert '{"wrong": 1}' in repair_text
    assert "title" in repair_text
