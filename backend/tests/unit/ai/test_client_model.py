"""The cost row records the model the API returned (C088)."""

from decimal import Decimal

from pydantic import BaseModel, Field

from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.prices import call_cost


class Title(BaseModel):
    title: str = Field(description="A short title.")


def _client(provider, prompts_dir, log):
    return AiClient(
        provider=provider,
        prompts_dir=prompts_dir,
        sleep=lambda s: None,
        cost_log=log,
    )


def test_cost_row_records_returned_model(provider, prompts_dir) -> None:
    provider.reply(
        '{"title": "Hi"}',
        model="muse-spark-1.3-contributor",
        prompt_tokens=1000,
        cached_tokens=0,
        completion_tokens=2000,
        reasoning_tokens=1500,
    )
    log = MemoryCostLog()
    _client(provider, prompts_dir, log).run("name_chat", {"topic": "hi"}, Title, app="tests")
    (row,) = log.rows
    assert row["model"] == "muse-spark-1.3-contributor"
    assert row["cost_usd"] == Decimal("0.0005")
    assert row["cost_usd"] == call_cost("muse-spark-1.3-contributor", 1000, 0, 2000)


def test_cost_row_falls_back_to_request_model(provider, prompts_dir) -> None:
    provider.reply('{"title": "Hi"}', prompt_tokens=100, cached_tokens=0, completion_tokens=200)
    log = MemoryCostLog()
    _client(provider, prompts_dir, log).run("name_chat", {"topic": "hi"}, Title, app="tests")
    (row,) = log.rows
    assert row["model"] == "muse-wonder-1.0"
    assert row["cost_usd"] == call_cost("muse-wonder-1.0", 100, 0, 200)
