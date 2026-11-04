"""The OpenAI provider, against a transport that never leaves the process."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from charie.llm.base import CallLimits, LLMError, LLMRequest, Message, Tags
from charie.llm.openai import OpenAIProvider, strict_safe
from llm_fixture import build_settings

ORG = uuid.uuid4()

#: What ``httpx.MockTransport`` calls.
Handler = Callable[[httpx.Request], httpx.Response]


class Plan(BaseModel):
    steps: list[str]


class Loose(BaseModel):
    """Has an optional field, so its schema cannot be sent as strict."""

    steps: list[str]
    note: str | None = None


class Strict(BaseModel):
    """Closed and fully required — the shape strict mode actually accepts."""

    model_config = ConfigDict(extra="forbid")

    steps: list[str]
    confident: bool


def request_for(
    *, schema: type[BaseModel] | None = None, system: str = "platform rules"
) -> LLMRequest:
    return LLMRequest(
        model="gpt-test",
        messages=[
            Message(role="system", content=system),
            Message(role="user", content="how many orders?"),
        ],
        tags=Tags(org_id=ORG, role="plan"),
        schema=schema,
        limits=CallLimits(max_output_tokens=256),
    )


def provider_for(handler: Handler) -> OpenAIProvider:
    return OpenAIProvider(
        api_key="test-key",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://api.openai.test/v1"
        ),
    )


def ok_body(text: str = '{"steps": ["a"]}', **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "gpt-test",
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        "usage": {"input_tokens": 11, "output_tokens": 7},
    }
    body.update(extra)
    return body


# --- What we send ---


async def test_system_messages_become_instructions_and_leave_the_turn_list() -> None:
    """This API takes system guidance as a top-level field."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=ok_body())

    await provider_for(handler).complete(request_for())

    assert seen["instructions"] == "platform rules"
    assert seen["input"] == [{"role": "user", "content": "how many orders?"}]
    assert all(item["role"] != "system" for item in seen["input"])


async def test_several_system_messages_keep_their_order() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=ok_body())

    request = LLMRequest(
        model="gpt-test",
        messages=[
            Message(role="system", content="L0 platform"),
            Message(role="system", content="L1 org"),
            Message(role="user", content="ask"),
        ],
        tags=Tags(org_id=ORG, role="plan"),
    )
    await provider_for(handler).complete(request)

    assert seen["instructions"] == "L0 platform\nL1 org"


async def test_the_key_travels_as_a_bearer_header_and_nowhere_else() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.headers))
        assert "test-key" not in request.content.decode()
        return httpx.Response(200, json=ok_body())

    await provider_for(handler).complete(request_for())

    assert seen["authorization"] == "Bearer test-key"


async def test_a_schema_is_sent_as_a_native_constrained_format() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=ok_body())

    await provider_for(handler).complete(request_for(schema=Plan))

    fmt = seen["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "Plan"
    assert "steps" in fmt["schema"]["properties"]


async def test_no_reasoning_effort_is_sent_unless_a_provider_asks_for_one() -> None:
    """The adapter learned to send `reasoning` for Meta (D-069)."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=ok_body())

    await provider_for(handler).complete(request_for(schema=Plan))

    assert "reasoning" not in seen


async def test_strict_is_claimed_only_when_the_schema_can_carry_it() -> None:
    """Rewriting a schema to satisfy strict mode would make an optional field mandatory."""
    captured: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=ok_body())

    provider = provider_for(handler)
    await provider.complete(request_for(schema=Plan))  # no additionalProperties
    await provider.complete(request_for(schema=Loose))  # optional field
    await provider.complete(request_for(schema=Strict))  # closed, all required

    assert captured[0]["text"]["format"]["strict"] is False
    assert captured[1]["text"]["format"]["strict"] is False
    assert captured[2]["text"]["format"]["strict"] is True


def test_a_nested_model_is_onlystrict_safe_when_every_definition_is() -> None:
    """Strictness is a property of the whole schema tree, not of its root."""

    class Nested(BaseModel):
        model_config = ConfigDict(extra="forbid")
        inner: Plan  # Plan is not closed

    class NestedStrict(BaseModel):
        model_config = ConfigDict(extra="forbid")
        inner: Strict

    assert strict_safe(Nested.model_json_schema()) is False
    assert strict_safe(NestedStrict.model_json_schema()) is True


async def test_no_schema_means_no_format_block() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=ok_body("prose"))

    await provider_for(handler).complete(request_for())

    assert "text" not in seen


# --- What we do with what comes back ---


async def test_the_answer_and_its_usage_are_read_back() -> None:
    completion = await provider_for(lambda _: httpx.Response(200, json=ok_body())).complete(
        request_for()
    )

    assert completion.text == '{"steps": ["a"]}'
    assert completion.provider == "openai"
    assert completion.usage.input_tokens == 11
    assert completion.usage.output_tokens == 7
    assert not completion.usage.estimated  # the provider counted these, we did not


async def test_the_cached_share_of_the_input_is_read_back() -> None:
    """Revision 0034. `input_tokens` is inclusive of the cached ones."""
    body = ok_body()
    body["usage"] = {
        "input_tokens": 11,
        "input_tokens_details": {"cached_tokens": 8},
        "output_tokens": 7,
    }
    completion = await provider_for(lambda _: httpx.Response(200, json=body)).complete(
        request_for()
    )

    assert completion.usage.input_tokens == 11
    assert completion.usage.cached_input_tokens == 8


async def test_no_cached_detail_is_unknown_rather_than_none_cached() -> None:
    """Two different claims, and the ledger reads this column as a measurement."""
    completion = await provider_for(lambda _: httpx.Response(200, json=ok_body())).complete(
        request_for()
    )

    assert completion.usage.cached_input_tokens is None


async def test_a_malformed_cached_count_is_unknown_not_zero() -> None:
    body = ok_body()
    body["usage"] = {
        "input_tokens": 11,
        "input_tokens_details": {"cached_tokens": "lots"},
        "output_tokens": 7,
    }
    completion = await provider_for(lambda _: httpx.Response(200, json=body)).complete(
        request_for()
    )

    assert completion.usage.cached_input_tokens is None


async def test_the_model_that_answered_is_recorded_not_the_one_asked_for() -> None:
    """A provider may serve a different snapshot than the alias requested."""
    body = ok_body()
    body["model"] = "gpt-test-2026-08-01"

    completion = await provider_for(lambda _: httpx.Response(200, json=body)).complete(
        request_for()
    )

    assert completion.model == "gpt-test-2026-08-01"


async def test_output_items_that_are_not_the_answer_are_skipped() -> None:
    """Reasoning summaries and tool calls are not the assistant's answer."""
    body = ok_body()
    body["output"] = [
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "internal"}]},
        {"type": "message", "content": [{"type": "output_text", "text": "the answer"}]},
    ]

    completion = await provider_for(lambda _: httpx.Response(200, json=body)).complete(
        request_for()
    )

    assert completion.text == "the answer"
    assert "internal" not in completion.text


async def test_a_refusal_is_an_error_and_is_not_retryable() -> None:
    """The model declined. Another provider would decline too — the chain exists for outages."""
    body = ok_body()
    body["output"] = [
        {"type": "message", "content": [{"type": "refusal", "refusal": "I can't help with that"}]}
    ]

    with pytest.raises(LLMError) as raised:
        await provider_for(lambda _: httpx.Response(200, json=body)).complete(request_for())

    assert "declined" in str(raised.value)
    assert not raised.value.retryable


async def test_truncation_is_reported_as_the_finish_reason() -> None:
    body = ok_body(status="incomplete", incomplete_details={"reason": "max_output_tokens"})

    completion = await provider_for(lambda _: httpx.Response(200, json=body)).complete(
        request_for()
    )

    assert completion.finish_reason == "max_output_tokens"


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(429, True), (500, True), (503, True), (400, False), (401, False), (404, False)],
)
async def test_the_status_code_decides_whether_to_try_again(status: int, retryable: bool) -> None:
    """This flag is the whole input to the retry and fallback decision."""
    body = {"error": {"type": "some_error", "code": "some_code", "message": "detail here"}}

    with pytest.raises(LLMError) as raised:
        await provider_for(lambda _: httpx.Response(status, json=body)).complete(request_for())

    assert raised.value.retryable is retryable
    assert str(status) in str(raised.value)


async def test_an_error_body_that_is_not_json_still_produces_a_usable_error() -> None:
    with pytest.raises(LLMError, match="502"):
        await provider_for(lambda _: httpx.Response(502, text="<html>gateway</html>")).complete(
            request_for()
        )


async def test_a_timeout_is_retryable_and_says_nothing_about_the_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMError) as raised:
        await provider_for(handler).complete(request_for())

    assert raised.value.retryable
    assert "did not respond in time" in str(raised.value)


async def test_a_transport_failure_does_not_leak_the_url() -> None:
    """httpx errors carry the full request URL in their repr."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    with pytest.raises(LLMError) as raised:
        await provider_for(handler).complete(request_for())

    assert "api.openai.test" not in str(raised.value)
    assert raised.value.__cause__ is None


async def test_the_provider_declares_native_schema_support() -> None:
    caps = provider_for(lambda _: httpx.Response(200, json=ok_body())).capabilities()

    assert caps.name == "openai"
    assert caps.supports_response_schema
    assert not caps.is_stub


def test_no_key_fails_with_the_fix_in_the_message() -> None:
    """The commonest first-run failure."""
    with pytest.raises(LLMError) as raised:
        OpenAIProvider(settings=build_settings(openai_api_key=None))

    message = str(raised.value)
    assert "OPENAI_API_KEY" in message
    assert "LLM_PROVIDERS" in message
    assert not raised.value.retryable


def test_a_configured_key_is_never_in_the_error_or_the_repr() -> None:
    """A provider key is a spending credential."""
    provider = OpenAIProvider(settings=build_settings(openai_api_key="sk-secret-value"))

    assert "sk-secret-value" not in repr(provider)
    assert "sk-secret-value" not in str(build_settings(openai_api_key="sk-secret-value"))
