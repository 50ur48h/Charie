"""Turning text into vectors, and writing down what that cost (architecture 5.5)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx

from charie.config import Settings, get_settings
from charie.db.models import EMBEDDING_DIMENSIONS
from charie.llm import budget, meter
from charie.llm.base import LLMError, Usage

__all__ = [
    "Embedder",
    "EmbeddingError",
    "OpenAIEmbedder",
    "embed_texts",
    "get_embedder",
    "reset_embedder",
]

#: What `response.json()` actually hands back.
JsonObject = dict[str, Any]

BASE_URL = "https://api.openai.com/v1"
EMBEDDINGS = "/embeddings"

#: Long enough for a full batch of chunks.
TIMEOUT_SECONDS = 60.0

HTTP_OK = 200
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500

#: Truncated for B-030's reason: provider error text describes the request.
ERROR_TEXT_LIMIT = 300


class EmbeddingError(LLMError):
    """An embedding call failed, already sanitized."""


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    """What one provider call returned, and what it cost."""

    vectors: tuple[tuple[float, ...], ...]
    usage: Usage
    model: str


class Embedder(Protocol):
    """What ingest and retrieval need from a provider."""

    @property
    def is_stub(self) -> bool:  # pragma: no cover - protocol
        ...

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:  # pragma: no cover - protocol
        ...


class OpenAIEmbedder:
    """The OpenAI embeddings endpoint, and nothing more."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = BASE_URL,
        client: httpx.AsyncClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved = settings if settings is not None else get_settings()
        key = api_key if api_key is not None else _key_from(resolved)
        chosen = model if model is not None else resolved.embeddings_model
        if not chosen:
            # No default in code, for D-017's reason.
            raise EmbeddingError(
                "EMBEDDINGS_MODEL is not set, so nothing can be embedded. "
                "Set it to a model this key may call — verify with GET /v1/models."
            )
        self._model = chosen
        self._expected = resolved.embeddings_dimensions
        self._client = client if client is not None else httpx.AsyncClient(base_url=base_url)
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    @property
    def model(self) -> str:
        return self._model

    @property
    def is_stub(self) -> bool:
        """Never. This one bills the account named by the key it holds."""
        return False

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(vectors=(), usage=Usage(), model=self._model)

        try:
            response = await self._client.post(
                EMBEDDINGS,
                headers=self._headers,
                json={"model": self._model, "input": list(texts)},
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            raise EmbeddingError(
                "the embedding provider did not respond in time", retryable=True
            ) from None
        except httpx.HTTPError:
            # Not chained and not detailed, for the reason `llm/openai.py` gives.
            raise EmbeddingError("could not reach the embedding provider", retryable=True) from None

        if response.status_code != HTTP_OK:
            raise _failure(response)

        return self._batch(cast(JsonObject, response.json()))

    def _batch(self, body: JsonObject) -> EmbeddingBatch:
        raw: object = body.get("data")
        if not isinstance(raw, list):
            raise EmbeddingError("the embedding provider returned no data")

        # Sorted by the provider's own index, never assumed to be in order.
        rows: list[JsonObject] = [
            cast(JsonObject, row) for row in cast(list[object], raw) if isinstance(row, dict)
        ]
        rows.sort(key=lambda row: _as_int(row.get("index")))

        vectors: list[tuple[float, ...]] = []
        for row in rows:
            embedding: object = row.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingError("the embedding provider returned a row with no vector")
            vector = tuple(_as_float(value) for value in cast(list[object], embedding))
            # Checked here, where the model id is in scope, rather than at the insert.
            if len(vector) != self._expected:
                raise EmbeddingError(
                    f"{self._model} returned {len(vector)} dimensions but this deployment "
                    f"stores {self._expected}. The column's width is fixed by a migration, "
                    "so a different model needs one — not only a configuration change."
                )
            vectors.append(vector)

        usage = body.get("usage")
        tokens = 0
        if isinstance(usage, dict):
            reported = cast(JsonObject, usage)
            tokens = _as_int(reported.get("prompt_tokens")) or _as_int(reported.get("total_tokens"))
        return EmbeddingBatch(
            vectors=tuple(vectors),
            # No output tokens: an embedding produces a vector, not text.
            usage=Usage(input_tokens=tokens, output_tokens=0, estimated=tokens == 0),
            model=self._model,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


#: The embedder this process built, keyed by the model id it was built for.
_INSTANCES: dict[str, Embedder] = {}


def get_embedder(settings: Settings | None = None) -> Embedder | None:
    """The embedder this deployment is configured for, or None if it has none."""
    resolved = settings if settings is not None else get_settings()
    model = resolved.embeddings_model
    if not model or resolved.openai_api_key is None:
        return None

    cached = _INSTANCES.get(model)
    if cached is not None:
        return cached

    # Before the first vector is written rather than at the insert that would reject it.
    check_dimensions(resolved)
    built = OpenAIEmbedder(settings=resolved)
    _INSTANCES[model] = built
    return built


def reset_embedder() -> None:
    """Forget the built instance. For tests, and for a settings change in one."""
    _INSTANCES.clear()


async def embed_texts(
    *,
    org_id: uuid.UUID,
    texts: Sequence[str],
    embedder: Embedder,
    run_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    settings: Settings | None = None,
) -> list[tuple[float, ...]]:
    """Embed everything, in batches, and meter every call including the failures."""
    resolved = settings if settings is not None else get_settings()
    size = max(1, resolved.embeddings_batch)
    model = getattr(embedder, "model", resolved.embeddings_model or "unknown")

    out: list[tuple[float, ...]] = []
    for start in range(0, len(texts), size):
        window = list(texts[start : start + size])
        # Before the call, never after: a ceiling enforced afterwards is a report.
        await budget.assert_within_limit(
            org_id=org_id, run_id=run_id, model=str(model), settings=resolved
        )
        began = time.perf_counter()
        try:
            batch = await embedder.embed(window)
        except LLMError as error:
            await meter.record(
                org_id=org_id,
                role="embed",
                tier="embed",
                provider=resolved.embeddings_provider,
                model=str(model),
                usage=Usage(),
                latency_ms=_elapsed(began),
                run_id=run_id,
                actor_user_id=actor_user_id,
                error=str(error)[:ERROR_TEXT_LIMIT],
                settings=resolved,
            )
            raise
        await meter.record(
            org_id=org_id,
            role="embed",
            tier="embed",
            provider=resolved.embeddings_provider,
            model=batch.model,
            usage=batch.usage,
            latency_ms=_elapsed(began),
            run_id=run_id,
            actor_user_id=actor_user_id,
            settings=resolved,
        )
        if len(batch.vectors) != len(window):
            raise EmbeddingError(
                f"asked for {len(window)} embeddings and got {len(batch.vectors)}; "
                "pairing them with the text would attach vectors to the wrong chunks"
            )
        out.extend(batch.vectors)
    return out


def _as_int(value: object) -> int:
    """A provider's number, or zero."""
    return int(value) if isinstance(value, int | float) else 0


def _as_float(value: object) -> float:
    """One component of a vector, and this one does raise."""
    if not isinstance(value, int | float):
        raise EmbeddingError("the embedding provider returned a non-numeric vector component")
    return float(value)


def _elapsed(began: float) -> int:
    return max(0, int((time.perf_counter() - began) * 1000))


def _key_from(settings: Settings) -> str:
    key = settings.openai_api_key
    if key is None:
        raise EmbeddingError("OPENAI_API_KEY is not set, so nothing can be embedded")
    return key.get_secret_value()


def _failure(response: httpx.Response) -> EmbeddingError:
    retryable = response.status_code == HTTP_TOO_MANY_REQUESTS or (
        response.status_code >= HTTP_SERVER_ERROR
    )
    return EmbeddingError(
        f"the embedding provider refused the request ({response.status_code}): {_detail(response)}",
        retryable=retryable,
    )


def _detail(response: httpx.Response) -> str:
    """The provider's own words about what it refused, truncated."""
    try:
        body = cast(object, response.json())
    except ValueError:
        return response.text[:ERROR_TEXT_LIMIT]
    if isinstance(body, dict):
        error: object = cast(JsonObject, body).get("error")
        if isinstance(error, dict):
            message: object = cast(JsonObject, error).get("message")
            if message is not None:
                return str(message)[:ERROR_TEXT_LIMIT]
    # Falls back to the raw body rather than to a re-serialised parse of it.
    return response.text[:ERROR_TEXT_LIMIT]


#: A last guard against the two constants drifting.
def check_dimensions(settings: Settings | None = None) -> None:
    """Raise if configuration and the column disagree about the vector's width."""
    resolved = settings if settings is not None else get_settings()
    if resolved.embeddings_dimensions != EMBEDDING_DIMENSIONS:
        raise EmbeddingError(
            f"EMBEDDINGS_DIMENSIONS is {resolved.embeddings_dimensions} but "
            f"knowledge_chunks.embedding is vector({EMBEDDING_DIMENSIONS}). "
            "One of them is wrong, and every insert would fail."
        )
