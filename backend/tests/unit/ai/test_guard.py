"""Guard: unmarked tests cannot reach Meta; only live_ai tests can."""

import pytest

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiRealCallBlocked
from charie.shared.ai.provider import AiRequest, MetaProvider, get_provider
from charie.shared.config import get_settings


def test_unmarked_test_cannot_call_meta(prompts_dir, monkeypatch) -> None:
    monkeypatch.setenv("META_API_KEY", "fake-key-for-guard-test")
    get_settings.cache_clear()
    client = AiClient(
        provider=None, prompts_dir=prompts_dir, sleep=lambda s: None, cost_log=MemoryCostLog()
    )
    with pytest.raises(AiRealCallBlocked):
        client.run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")


def test_unmarked_provider_complete_is_blocked() -> None:
    provider = MetaProvider(api_key="fake-key-for-guard-test")
    request = AiRequest(
        job="name_chat",
        model="muse-wonder-1.0",
        messages=[{"role": "user", "content": "hi"}],
        form_schema={"type": "object"},
        reasoning_effort="low",
        max_output_tokens=512,
        timeout_seconds=60,
    )
    with pytest.raises(AiRealCallBlocked):
        provider.complete(request)


def test_provider_factory_still_builds_with_fake_key(monkeypatch) -> None:
    monkeypatch.setenv("META_API_KEY", "fake-key-for-guard-test")
    get_settings.cache_clear()
    assert isinstance(get_provider("meta"), MetaProvider)
