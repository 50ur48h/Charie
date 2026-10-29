"""Spending: thresholds, paused calls, owner-local month."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog, usage_row
from charie.shared.ai.errors import SpendingPaused
from charie.shared.ai.spending import month_spent_rows, spending_state


def test_ok_below_warning() -> None:
    assert spending_state(Decimal("7.99"), 10, 80) == "ok"


def test_warn_at_80_percent() -> None:
    assert spending_state(Decimal("8"), 10, 80) == "warn"


def test_paused_at_limit() -> None:
    assert spending_state(Decimal("10"), 10, 80) == "paused"
    assert spending_state(Decimal("11"), 10, 80) == "paused"


def test_month_follows_time_zone() -> None:
    rows = [
        usage_row(
            job="name_chat",
            app="chat",
            model="m",
            prompt_tokens=0,
            cached_tokens=0,
            completion_tokens=0,
            reasoning_tokens=0,
            cost_usd=Decimal("2.00"),
            duration_ms=0,
            status="ok",
            at=datetime(2026, 10, 1, 0, 1, tzinfo=UTC),
        ),
    ]
    # The same instant is October in Kolkata but still September in New York.
    assert month_spent_rows(rows, datetime(2026, 10, 15), "Asia/Kolkata") == Decimal("2.00")
    assert month_spent_rows(rows, datetime(2026, 10, 15), "America/New_York") == Decimal("0")


def test_repair_rechecks_spending(provider, prompts_dir) -> None:
    """The first reply's cost can hit the limit; the repair then stops."""
    log = MemoryCostLog(
        limit=0.001,
        warn_percent=80,
        rows=[
            usage_row(
                job="name_chat",
                app="chat",
                model="m",
                prompt_tokens=0,
                cached_tokens=0,
                completion_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("0.0008"),
                duration_ms=0,
                status="ok",
            )
        ],
    )
    provider.reply("not json", prompt_tokens=100, completion_tokens=20)
    provider.reply('{"title": "Hi"}', prompt_tokens=100, completion_tokens=20)
    client = AiClient(
        provider=provider, prompts_dir=prompts_dir, sleep=lambda s: None, cost_log=log
    )
    with pytest.raises(SpendingPaused):
        client.run("name_chat", {"topic": "t"}, ChatTitle, app="chat")
    assert len(provider.calls) == 1
    assert [row["status"] for row in log.rows] == ["ok", "retried"]


def test_paused_makes_no_request(provider, prompts_dir) -> None:
    log = MemoryCostLog(
        limit=10,
        warn_percent=80,
        rows=[
            usage_row(
                job="name_chat",
                app="chat",
                model="m",
                prompt_tokens=0,
                cached_tokens=0,
                completion_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("10.00"),
                duration_ms=0,
                status="ok",
            )
        ],
    )
    client = AiClient(
        provider=provider, prompts_dir=prompts_dir, sleep=lambda s: None, cost_log=log
    )
    with pytest.raises(SpendingPaused):
        client.run("name_chat", {"topic": "t"}, ChatTitle, app="chat")
    assert provider.calls == []
