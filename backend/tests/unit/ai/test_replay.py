"""Replay store: fingerprints, saving, replaying, directory default."""

import pytest

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiReplayMissing
from charie.shared.ai.provider import MetaProvider
from charie.shared.ai.replay import ReplayStore, fingerprint
from charie.shared.config import get_settings


def _parts(**overrides):
    base = {
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
        "schema": {"type": "object"},
        "reasoning_effort": "low",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "change",
    [
        {"model": "other"},
        {"messages": [{"role": "user", "content": "bye"}]},
        {"schema": {"type": "string"}},
        {"reasoning_effort": "high"},
    ],
)
def test_fingerprint_changes_with_each_part(change) -> None:
    assert fingerprint(_parts()) != fingerprint(_parts(**change))


def _write_prompt(prompts_dir) -> None:
    (prompts_dir / "name_chat.md").write_text(
        "## Rules\nShort.\n\n## Examples\nNone.\n\n## Task\nTitle: {{topic}}.\n",
        encoding="utf-8",
    )


class FakeTransport:
    """Stands in for the network inside `MetaProvider`."""

    def __init__(self) -> None:
        self.calls = 0
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls += 1
        from types import SimpleNamespace

        message = SimpleNamespace(content='{"title": "Hi"}', refusal=None)
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _client(transport, prompts_dir, log, mode: str) -> AiClient:
    return AiClient(
        provider=MetaProvider(api_key="not-a-key", _client=transport),
        prompts_dir=prompts_dir,
        sleep=lambda s: None,
        cost_log=log,
        replay_mode=mode,
    )


def test_record_saves_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_REPLAY_DIR", str(tmp_path / "replays"))
    get_settings.cache_clear()
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    _write_prompt(prompts)
    _client(FakeTransport(), prompts, MemoryCostLog(), "record").run(
        "name_chat", {"topic": "hi"}, ChatTitle, app="chat"
    )
    assert list((tmp_path / "replays" / "name_chat").glob("*.json"))


def test_replay_uses_file_without_calling(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_REPLAY_DIR", str(tmp_path / "replays"))
    get_settings.cache_clear()
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    _write_prompt(prompts)
    transport = FakeTransport()
    _client(transport, prompts, MemoryCostLog(), "record").run(
        "name_chat", {"topic": "hi"}, ChatTitle, app="chat"
    )
    assert transport.calls == 1
    replaying = _client(transport, prompts, MemoryCostLog(), "replay")
    second = replaying.run("name_chat", {"topic": "hi"}, ChatTitle, app="chat")
    assert second.title == "Hi"
    assert transport.calls == 1


def test_replay_needs_no_api_key(tmp_path, monkeypatch) -> None:
    """A replay loads the file without building a provider (no key needed)."""
    from charie.shared.config import get_settings

    monkeypatch.setenv("AI_REPLAY_DIR", str(tmp_path / "replays"))
    get_settings.cache_clear()
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    _write_prompt(prompts)
    _client(FakeTransport(), prompts, MemoryCostLog(), "record").run(
        "name_chat", {"topic": "hi"}, ChatTitle, app="chat"
    )
    monkeypatch.delenv("META_API_KEY", raising=False)
    get_settings.cache_clear()
    assert get_settings().meta_api_key is None
    keyless = AiClient(
        provider=None,
        prompts_dir=prompts,
        sleep=lambda s: None,
        cost_log=MemoryCostLog(),
        replay_mode="replay",
    )
    assert keyless.run("name_chat", {"topic": "hi"}, ChatTitle, app="chat").title == "Hi"


def test_replays_cost_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_REPLAY_DIR", str(tmp_path / "replays"))
    get_settings.cache_clear()
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    _write_prompt(prompts)
    _client(FakeTransport(), prompts, MemoryCostLog(), "record").run(
        "name_chat", {"topic": "hi"}, ChatTitle, app="chat"
    )
    log = MemoryCostLog()
    _client(FakeTransport(), prompts, log, "replay").run(
        "name_chat", {"topic": "hi"}, ChatTitle, app="chat"
    )
    assert len(log.rows) == 1 and log.rows[0]["cost_usd"] == 0


def test_missing_replay_is_an_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_REPLAY_DIR", str(tmp_path / "replays"))
    get_settings.cache_clear()
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    _write_prompt(prompts)
    with pytest.raises(AiReplayMissing):
        _client(FakeTransport(), prompts, MemoryCostLog(), "replay").run(
            "name_chat", {"topic": "hi"}, ChatTitle, app="chat"
        )


def test_store_round_trip(tmp_path) -> None:
    store = ReplayStore(tmp_path)
    record = {"content": '{"title": "Hi"}', "usage": {"prompt_tokens": 1}}
    store.save("name_chat", "abc123", record)
    assert store.load("name_chat", "abc123") == record
    with pytest.raises(AiReplayMissing):
        store.load("name_chat", "nope")
