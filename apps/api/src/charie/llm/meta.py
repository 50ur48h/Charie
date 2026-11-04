"""The Meta Model API provider (DECISIONS D-069)."""

from __future__ import annotations

import httpx

from charie.config import Settings, get_settings
from charie.llm.base import LLMError
from charie.llm.responses import ResponsesProvider

__all__ = ["BASE_URL", "MetaProvider"]

#: Meta's documented endpoint for the Responses, Chat Completions and Messages protocols alike.
BASE_URL = "https://api.meta.ai/v1"


class MetaProvider(ResponsesProvider):
    """The Responses client, aimed at the Meta Model API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved = settings if settings is not None else get_settings()
        super().__init__(
            api_key=api_key if api_key is not None else _key_from(resolved),
            base_url=base_url,
            client=client,
            name="meta",
            reasoning_effort=resolved.meta_reasoning_effort,
        )


def _key_from(settings: Settings) -> str:
    if settings.meta_api_key is None:
        raise LLMError(
            "META_API_KEY is not set, so the meta provider cannot be used. "
            "Set it in .env, or remove 'meta' from LLM_PROVIDERS.",
            retryable=False,
        )
    return settings.meta_api_key.get_secret_value()
