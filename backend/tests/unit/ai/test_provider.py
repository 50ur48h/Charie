"""The Meta provider: what it sends and how it reads the reply."""

from types import SimpleNamespace

from charie.shared.ai.provider import AiRequest, MetaProvider


def _request(**overrides):
    base = {
        "model": "muse-wonder-1.0",
        "messages": [{"role": "user", "content": "Hi."}],
        "form_schema": {"type": "object"},
        "reasoning_effort": "low",
        "max_output_tokens": 2000,
        "timeout_seconds": 60,
        "prompt_cache_key": "name_chat",
        "job": "name_chat",
    }
    base.update(overrides)
    return AiRequest(**base)


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.sent = None

    def create(self, **kwargs):
        self.sent = kwargs
        return self.response


class FakeOpenAI:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=FakeCompletions(response))


def _response(content, prompt=100, cached=10, completion=20, reasoning=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached),
            completion_tokens=completion,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
        ),
        model="muse-wonder-1.0",
    )


def test_request_has_form_effort_and_cache_key():
    fake = FakeOpenAI(_response('{"title": "Sales up"}'))
    provider = MetaProvider(api_key="test", _client=fake)
    reply = provider.complete(_request())
    sent = provider._client.chat.completions.sent
    assert sent["model"] == "muse-wonder-1.0"
    assert sent["reasoning_effort"] == "low"
    assert sent["max_completion_tokens"] == 2000
    assert sent["timeout"] == 60
    assert sent["prompt_cache_key"] == "name_chat"
    assert sent["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "name_chat", "schema": {"type": "object"}, "strict": True},
    }
    assert reply.content == '{"title": "Sales up"}'


def test_usage_numbers_read():
    provider = MetaProvider(api_key="test")
    provider._client = FakeOpenAI(_response("{}", 100, 10, 20, 5))
    reply = provider.complete(_request())
    assert (reply.prompt_tokens, reply.cached_tokens) == (100, 10)
    assert (reply.completion_tokens, reply.reasoning_tokens) == (20, 5)


def test_missing_usage_counts_zero():
    bare = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
        usage=SimpleNamespace(prompt_tokens=None, completion_tokens=None),
        model="",
    )
    provider = MetaProvider(api_key="test")
    provider._client = FakeOpenAI(bare)
    reply = provider.complete(_request())
    assert (reply.prompt_tokens, reply.cached_tokens) == (0, 0)
    assert (reply.completion_tokens, reply.reasoning_tokens) == (0, 0)
