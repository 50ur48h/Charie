"""The Meta provider: one small wrapper around the OpenAI-style API."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from charie.shared.ai.errors import AiError


@dataclass
class AiRequest:
    """Everything one AI call sends."""

    model: str
    messages: list[dict[str, str]]
    form_schema: dict[str, Any]
    reasoning_effort: str
    max_output_tokens: int
    timeout_seconds: int
    prompt_cache_key: str | None = None
    job: str = ""


@dataclass
class AiReply:
    """What came back: content plus the token counts for the cost log."""

    content: str
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    model: str = ""


@dataclass
class AiCallError(Exception):
    """A failed attempt the client may retry: status, code and message."""

    status: int | None = None
    code: str = ""
    message: str = ""
    retry_after: float | None = None


class Provider(Protocol):
    """One method; Meta implements it today, Claude can later."""

    def complete(self, request: AiRequest) -> AiReply: ...


META_API_BASE_URL = "https://api.meta.ai/v1"


@dataclass
class MetaProvider:
    """Calls Meta's OpenAI-style API. Our own retries only (`max_retries=0`)."""

    replayable = True

    api_key: str
    base_url: str = META_API_BASE_URL
    _client: Any = field(default=None, repr=False)

    def client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url, max_retries=0)
        return self._client

    def complete(self, request: AiRequest) -> AiReply:
        import openai

        try:
            response = self.client().chat.completions.create(
                model=request.model,
                messages=request.messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.job,
                        "schema": request.form_schema,
                        "strict": True,
                    },
                },
                reasoning_effort=request.reasoning_effort,
                max_completion_tokens=request.max_output_tokens,
                timeout=request.timeout_seconds,
                **(
                    {"prompt_cache_key": request.prompt_cache_key}
                    if request.prompt_cache_key
                    else {}
                ),
            )
        except openai.RateLimitError as err:
            raise AiCallError(
                status=429,
                code="rate_limited",
                message=str(err),
                retry_after=_retry_after(err),
            ) from err
        except (openai.APITimeoutError, openai.APIConnectionError) as err:
            raise AiCallError(status=None, code="connection", message=str(err)) from err
        except openai.APIStatusError as err:
            raise AiCallError(
                status=err.status_code, code=_error_code(err), message=str(err)
            ) from err
        return _to_reply(response, request.model)

    def __call__(self, request: AiRequest) -> AiReply:
        return self.complete(request)


def get_provider(name: str) -> Provider:
    """The provider by name; `meta` is the only one today."""
    if name == "meta":
        from charie.shared.config import get_settings, require_env

        return MetaProvider(
            api_key=require_env("META_API_KEY"),
            base_url=get_settings().meta_api_base_url,
        )
    raise AiError("unknown_provider", f"Unknown AI provider: `{name}`.")


def _retry_after(err: Any) -> float | None:
    try:
        value = err.response.headers.get("retry-after")
    except Exception:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _error_code(err: Any) -> str:
    try:
        data = err.body if isinstance(err.body, dict) else {}
        code = data.get("code") or data.get("error", {}).get("code", "")
    except Exception:
        code = ""
    return str(code)


def _to_reply(response: Any, model: str) -> AiReply:
    content = response.choices[0].message.content or ""
    usage = response.usage
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    return AiReply(
        content=content,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        cached_tokens=getattr(prompt_details, "cached_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        reasoning_tokens=getattr(completion_details, "reasoning_tokens", 0) or 0,
        model=getattr(response, "model", "") or model,
    )


def short_reason(error: AiCallError) -> str:
    """The first line of the message, for `ai_api_error`."""
    return (error.message or "").split("\n")[0][:200]
