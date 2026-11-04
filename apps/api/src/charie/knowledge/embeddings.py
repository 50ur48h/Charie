"""Turning text into vectors, and writing down what that cost (architecture 5.5)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from charie.config import Settings, get_settings
from charie.llm import budget, meter
from charie.llm.base import LLMError, Usage

__all__ = [
    "Embedder",
    "EmbeddingError",
    "embed_texts",
    "get_embedder",
]

#: How many texts go in one embedding call.
BATCH_SIZE = 64

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


def get_embedder(settings: Settings | None = None) -> Embedder | None:
    """None: Charie calls only Meta models, so tables and documents are searched by wording."""
    del settings
    return None


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
    model = str(getattr(embedder, "model", "unknown"))
    provider = str(getattr(embedder, "provider", "unknown"))

    out: list[tuple[float, ...]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        window = list(texts[start : start + BATCH_SIZE])
        # Before the call, never after: a ceiling enforced afterwards is a report.
        await budget.assert_within_limit(
            org_id=org_id, run_id=run_id, model=model, settings=resolved
        )
        began = time.perf_counter()
        try:
            batch = await embedder.embed(window)
        except LLMError as error:
            await meter.record(
                org_id=org_id,
                role="embed",
                tier="embed",
                provider=provider,
                model=model,
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
            provider=provider,
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


def _elapsed(began: float) -> int:
    return max(0, int((time.perf_counter() - began) * 1000))
