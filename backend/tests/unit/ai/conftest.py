"""A scripted provider: queued replies or errors, no network ever."""

import pytest

from charie.shared.ai.provider import AiReply, AiRequest
from charie.shared.config import get_settings


@pytest.fixture(autouse=True)
def _fresh_settings():
    """Each test reads the environment fresh; no settings leak between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class ScriptedProvider:
    """Queue replies or errors; `calls` records each request."""

    def __init__(self) -> None:
        self.queued: list = []
        self.calls: list[AiRequest] = []

    def reply(self, content: str, **usage) -> "ScriptedProvider":
        self.queued.append(AiReply(content=content, **usage))
        return self

    def fail(self, error: Exception) -> "ScriptedProvider":
        self.queued.append(error)
        return self

    def complete(self, request: AiRequest) -> AiReply:
        self.calls.append(request)
        if not self.queued:
            raise AssertionError("ScriptedProvider has nothing queued.")
        next_item = self.queued.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


@pytest.fixture()
def provider():
    return ScriptedProvider()


@pytest.fixture()
def prompts_dir(tmp_path):
    (tmp_path / "name_chat.md").write_text(
        "## Rules\n1. Short titles.\n\n## Examples\nNone.\n\n## Task\nTitle this: {{topic}}.\n",
        encoding="utf-8",
    )
    return tmp_path
