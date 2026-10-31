"""Embeddings through Azure OpenAI for document and knowledge search (05, 08).

1536 dimensions by default; every returned vector is checked against the
requested size. Real calls use persistent cost accounting; saved replays
are reused without touching Azure.
"""

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_chain,
    wait_fixed,
)

from charie.shared.ai.client import BACKOFFS, MAX_RETRIES
from charie.shared.ai.cost_log import DbCostLog, MemoryCostLog, usage_row
from charie.shared.ai.errors import (
    AiApiError,
    AiError,
    AiReplayMissing,
    AiUnavailable,
    SpendingPaused,
)
from charie.shared.ai.prices import call_cost
from charie.shared.ai.replay import ReplayStore, default_dir
from charie.shared.ai.spending import spending_state
from charie.shared.config import get_settings

MODEL = "text-embedding-3-large"
API_VERSION = "2024-10-21"
BATCH_SIZE = 20  # Stays under per-call token limits.
DIMS = 1536  # Contract size: requested from Azure and validated.
DEPLOYMENT = "embed-3-large"  # Matches infra/ai.bicep.
JOB = "embed_texts"


@dataclass(frozen=True)
class EmbeddingResult:
    """One vector per input text, plus billed tokens and cost."""

    vectors: list[list[float]]
    prompt_tokens: int
    cost_usd: Decimal


def embed_texts(
    texts: list[str],
    *,
    provider: str = "azure",
    dimensions: int | None = None,
    batch_size: int = BATCH_SIZE,
    endpoint: str | None = None,
    key: str | None = None,
    deployment: str | None = None,
    api_version: str | None = None,
    app: str = "learner",
    learning_run_id: int | None = None,
    cost_log: Any = None,
    sleep=time.sleep,
    _embed_batch: Callable[[list[str], int], tuple[list[list[float]], int]] | None = None,
) -> EmbeddingResult:
    """Embed each text. Fake provider gives deterministic test vectors."""
    dims = dimensions or DIMS
    log = cost_log if cost_log is not None else _default_log(provider)
    _check_spending(log)
    started = time.monotonic()
    if provider == "fake":
        result = EmbeddingResult(
            vectors=[_fake_vector(text, dims) for text in texts],
            prompt_tokens=0,
            cost_usd=Decimal("0"),
        )
    else:
        result = _embed_reused_or_live(
            texts,
            dims=dims,
            batch_size=batch_size,
            endpoint=endpoint,
            key=key,
            deployment=deployment,
            api_version=api_version,
            sleep=sleep,
            _embed_batch=_embed_batch,
        )
    log.add(
        usage_row(
            job=JOB,
            app=app,
            model=MODEL,
            prompt_tokens=result.prompt_tokens,
            cached_tokens=0,
            completion_tokens=0,
            reasoning_tokens=0,
            cost_usd=result.cost_usd,
            duration_ms=_elapsed_ms(started),
            error=None,
            status="ok",
            learning_run_id=learning_run_id,
        )
    )
    return result


def _default_log(provider: str) -> Any:
    # Real calls persist cost rows; fakes stay out of the database.
    return MemoryCostLog() if provider == "fake" else DbCostLog()


def _check_spending(log: Any) -> None:
    limit, warn = log.limits()
    if spending_state(log.month_spent(datetime.now(UTC)), limit, warn) == "paused":
        raise SpendingPaused()


def _replay_mode() -> str:
    return get_settings().ai_replay


def _embed_reused_or_live(
    texts: list[str],
    *,
    dims: int,
    batch_size: int,
    endpoint: str | None,
    key: str | None,
    deployment: str | None,
    api_version: str | None,
    sleep,
    _embed_batch,
) -> EmbeddingResult:
    # A saved replay wins: no Azure call, no credentials, no cost. An
    # explicitly injected batch function is the test's stand-in for Azure,
    # so it bypasses the replay lookup (the network is still never touched).
    digest = _fingerprint({"model": MODEL, "dimensions": dims, "texts": texts})
    store = ReplayStore(default_dir())
    if _embed_batch is None:
        try:
            record = store.load(JOB, digest)
        except AiReplayMissing:
            if _replay_mode() == "replay":
                raise
        else:
            vectors = _checked_vectors(record["vectors"], dims)
            return EmbeddingResult(
                vectors=vectors, prompt_tokens=record["prompt_tokens"], cost_usd=Decimal("0")
            )
    result = _embed_live(
        texts,
        dims=dims,
        batch_size=batch_size,
        endpoint=endpoint,
        key=key,
        deployment=deployment,
        api_version=api_version,
        sleep=sleep,
        _embed_batch=_embed_batch,
    )
    if _replay_mode() == "record":
        store.save(JOB, digest, {"vectors": result.vectors, "prompt_tokens": result.prompt_tokens})
    return result


def _embed_live(
    texts: list[str],
    *,
    dims: int,
    batch_size: int,
    endpoint: str | None,
    key: str | None,
    deployment: str | None,
    api_version: str | None,
    sleep,
    _embed_batch,
) -> EmbeddingResult:
    call = _embed_batch or _live_batch(endpoint, key, deployment, api_version, dims)
    retryer = Retrying(
        stop=stop_after_attempt(MAX_RETRIES + 1),
        wait=wait_chain(*[wait_fixed(s) for s in BACKOFFS]),
        retry=retry_if_exception(lambda err: not isinstance(err, AiError)),
        reraise=False,
        sleep=sleep,
    )
    vectors: list[list[float]] = []
    prompt_tokens = 0
    try:
        for start in range(0, len(texts), batch_size):
            batch_vectors, batch_tokens = retryer(call, texts[start : start + batch_size], dims)
            vectors.extend(batch_vectors)
            prompt_tokens += batch_tokens
    except RetryError as err:
        raise AiUnavailable() from err
    except AiError:
        raise
    except Exception as err:
        raise AiApiError(f"Could not embed texts: {err}.") from err
    return EmbeddingResult(
        vectors=_checked_vectors(vectors, dims),
        prompt_tokens=prompt_tokens,
        cost_usd=call_cost(MODEL, prompt_tokens, 0, 0),
    )


def _live_batch(
    endpoint: str | None,
    key: str | None,
    deployment: str | None,
    api_version: str | None,
    dims: int,
):
    settings = get_settings()
    resolved_endpoint = endpoint or settings.azure_openai_endpoint
    secret = key or (
        settings.azure_openai_key.get_secret_value() if settings.azure_openai_key else None
    )
    if not resolved_endpoint or not secret:
        raise AiError(
            "openai_misconfigured",
            "Embeddings need AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY in .env.",
        )
    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key=secret,
        api_version=api_version or settings.azure_openai_api_version or API_VERSION,
        azure_endpoint=resolved_endpoint,
    )
    resolved_deployment = deployment or settings.azure_openai_embedding_deployment or DEPLOYMENT

    def _call(batch: list[str], batch_dims: int) -> tuple[list[list[float]], int]:
        response = client.embeddings.create(
            input=batch, model=resolved_deployment, dimensions=batch_dims
        )
        return [list(item.embedding) for item in response.data], response.usage.prompt_tokens

    return _call


def _checked_vectors(vectors: list[list[float]], dims: int) -> list[list[float]]:
    for vector in vectors:
        if len(vector) != dims:
            raise AiError(
                "embed_bad_dimensions",
                f"Expected a {dims}-number embedding, got {len(vector)} numbers.",
            )
    return vectors


def _fake_vector(text: str, dims: int) -> list[float]:
    """Deterministic unit vector from the text hash; tests only."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [(digest[i % len(digest)] / 127.5) - 1.0 for i in range(dims)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


def _fingerprint(parts: dict[str, Any]) -> str:
    compact = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
