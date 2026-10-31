"""Reader: fake layout, plain timeout error, replay, usage rows (P08.1)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from charie.shared.ai.cost_log import MemoryCostLog, usage_row
from charie.shared.ai.errors import AiError, AiUnavailable, SpendingPaused
from charie.shared.config import get_settings
from charie.shared.documents.reader import read_document


def test_fake_layout() -> None:
    doc = read_document(b"%PDF", filename="plan.pdf", provider="fake")
    assert doc.filename == "plan.pdf"
    assert "plan.pdf" in doc.markdown
    assert doc.page_count == 1
    assert doc.cost_usd == Decimal("0")


def test_timeout_plain_error() -> None:
    def _hang(data: bytes) -> tuple[str, int]:
        raise TimeoutError("poll timed out")

    with pytest.raises(AiUnavailable) as exc:
        read_document(
            b"%PDF",
            filename="a.pdf",
            provider="azure",
            cost_log=MemoryCostLog(),
            sleep=lambda _: None,
            _analyze=_hang,
        )
    assert isinstance(exc.value, AiError)
    assert "try again" in exc.value.message


def test_spending_paused_before_any_call() -> None:
    log = MemoryCostLog(
        rows=[
            usage_row(
                job="read_document",
                app="learner",
                model="prebuilt-layout",
                prompt_tokens=0,
                cached_tokens=0,
                completion_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("200"),
                duration_ms=1,
                status="ok",
                at=datetime.now(UTC),
            )
        ]
    )
    with pytest.raises(SpendingPaused):
        read_document(b"%PDF", filename="a.pdf", provider="fake", cost_log=log)
    assert len(log.rows) == 1  # No new row for the blocked call.


def test_replay_without_network(tmp_path, monkeypatch) -> None:
    texts = b"%PDF recorded"
    monkeypatch.setenv("AI_REPLAY", "record")
    monkeypatch.setenv("AI_REPLAY_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        read_document(
            texts,
            filename="a.pdf",
            provider="azure",
            cost_log=MemoryCostLog(),
            sleep=lambda _: None,
            _analyze=lambda data: ("# recorded\n", 3),
        )
    finally:
        get_settings.cache_clear()
    monkeypatch.setenv("AI_REPLAY", "replay")
    for name in ("AZURE_DI_ENDPOINT", "AZURE_DI_KEY"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    try:
        log = MemoryCostLog()
        doc = read_document(texts, filename="a.pdf", provider="azure", cost_log=log)
    finally:
        get_settings.cache_clear()
    assert doc.markdown == "# recorded\n"
    assert doc.page_count == 3
    assert doc.cost_usd == Decimal("0")  # Replays are free, like Meta replays.
    assert len(log.rows) == 1
    assert log.rows[0]["cost_usd"] == Decimal("0")  # Replays are free.


def test_usage_logged() -> None:
    log = MemoryCostLog()
    read_document(b"%PDF", filename="a.pdf", provider="fake", cost_log=log)
    assert len(log.rows) == 1
    row = log.rows[0]
    assert (row["job"], row["model"], row["status"]) == (
        "read_document",
        "prebuilt-layout",
        "ok",
    )
    assert row["cost_usd"] == Decimal("0")


def test_misconfigured_without_credentials() -> None:
    with pytest.raises(AiError):
        read_document(b"%PDF", filename="a.pdf", cost_log=MemoryCostLog())
