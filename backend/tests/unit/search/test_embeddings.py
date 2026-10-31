"""Embeddings: 1536 dims, replay, usage rows (P08.1, no network)."""

from decimal import Decimal

import pytest

from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.errors import AiError, AiReplayMissing, SpendingPaused
from charie.shared.config import get_settings
from charie.shared.search.embeddings import embed_texts


def test_1536_dimensions() -> None:
    result = embed_texts(["hello", "world"], provider="fake")
    assert len(result.vectors) == 2
    assert all(len(vector) == 1536 for vector in result.vectors)
    assert result.vectors[0] != result.vectors[1]
    assert result.cost_usd == Decimal("0")


def test_wrong_size_vector_rejected() -> None:
    def _short(batch: list[str], dims: int) -> tuple[list[list[float]], int]:
        assert dims == 1536
        return [[0.0] * 8 for _ in batch], 10

    with pytest.raises(AiError) as exc:
        embed_texts(
            ["a"],
            provider="azure",
            cost_log=MemoryCostLog(),
            sleep=lambda _: None,
            _embed_batch=_short,
        )
    assert exc.value.code == "embed_bad_dimensions"


def test_replay_without_network(tmp_path, monkeypatch) -> None:
    texts = ["first doc", "second doc"]
    monkeypatch.setenv("AI_REPLAY", "record")
    monkeypatch.setenv("AI_REPLAY_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        recorded = embed_texts(
            texts,
            provider="azure",
            cost_log=MemoryCostLog(),
            sleep=lambda _: None,
            _embed_batch=lambda batch, dims: ([[0.5] * dims for _ in batch], 12),
        )
    finally:
        get_settings.cache_clear()
    assert all(len(vector) == 1536 for vector in recorded.vectors)
    monkeypatch.setenv("AI_REPLAY", "replay")
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    try:
        log = MemoryCostLog()
        replayed = embed_texts(texts, provider="azure", cost_log=log)
    finally:
        get_settings.cache_clear()
    assert replayed.vectors == recorded.vectors
    assert replayed.cost_usd == Decimal("0")  # Replays are free.
    assert len(log.rows) == 1


def test_replay_mode_without_record_never_calls_azure(monkeypatch) -> None:
    monkeypatch.setenv("AI_REPLAY", "replay")
    monkeypatch.setenv("AI_REPLAY_DIR", "backend/tests/replays/")
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_KEY"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(AiReplayMissing):
            embed_texts(["unseen text"], provider="azure", cost_log=MemoryCostLog())
    finally:
        get_settings.cache_clear()


def test_usage_logged() -> None:
    log = MemoryCostLog()
    result = embed_texts(
        ["a", "b"],
        provider="azure",
        cost_log=log,
        sleep=lambda _: None,
        _embed_batch=lambda batch, dims: ([[0.0] * dims for _ in batch], 100),
    )
    assert result.cost_usd == Decimal("100") * Decimal("0.13") / Decimal(1_000_000)
    assert len(log.rows) == 1
    row = log.rows[0]
    assert (row["job"], row["model"], row["status"]) == (
        "embed_texts",
        "text-embedding-3-large",
        "ok",
    )
    assert row["prompt_tokens"] == 100


def test_batches_of_twenty() -> None:
    seen: list[tuple[int, int]] = []

    def _seam(batch: list[str], dims: int) -> tuple[list[list[float]], int]:
        seen.append((len(batch), dims))
        return [[0.0] * dims for _ in batch], 10 * len(batch)

    result = embed_texts(
        [f"doc {n}" for n in range(45)],
        provider="azure",
        cost_log=MemoryCostLog(),
        sleep=lambda _: None,
        _embed_batch=_seam,
    )
    assert seen == [(20, 1536), (20, 1536), (5, 1536)]
    assert len(result.vectors) == 45


def test_transient_batch_errors_retry() -> None:
    calls: list[int] = []

    def _flaky(batch: list[str], dims: int) -> tuple[list[list[float]], int]:
        calls.append(len(batch))
        if len(calls) < 3:
            raise ConnectionError("throttled")
        return [[1.0] * dims for _ in batch], 7

    result = embed_texts(
        ["a"],
        provider="azure",
        cost_log=MemoryCostLog(),
        sleep=lambda _: None,
        _embed_batch=_flaky,
    )
    assert calls == [1, 1, 1]
    assert result.prompt_tokens == 7


def test_spending_paused_before_any_call() -> None:
    log = MemoryCostLog(limit=0.0)
    with pytest.raises(SpendingPaused):
        embed_texts(["a"], provider="fake", cost_log=log)
