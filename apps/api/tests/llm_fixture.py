"""What the LLM suite is configured with."""

from __future__ import annotations

import uuid

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine

from charie.config import Settings

#: One provider, three tiers, obviously fake model ids.
FAKE_MODELS = {"fake": {"small": "fake-small", "mid": "fake-mid", "strong": "fake-strong"}}


def build_settings(**overrides: object) -> Settings:
    """Settings with one configured provider and no prices."""
    values: dict[str, object] = {
        "env": "ci",
        "build_env": "dev",
        "llm_providers": ("fake",),
        "llm_models": FAKE_MODELS,
        "llm_role_map": {},
        "llm_prices": {},
        "llm_run_cost_limit_usd": None,
        "llm_refuse_unpriced_when_capped": True,
        "openai_api_key": None,
        "anthropic_api_key": None,
        "meta_api_key": None,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # pyright: ignore[reportArgumentType, reportCallIssue]


async def seed_run(url: URL, org_id: uuid.UUID) -> uuid.UUID:
    """A real conversation and a real run, and the run's id."""
    run_id = uuid.uuid4()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config('app.org_id', :org, true)"), {"org": str(org_id)}
            )
            conversation_id = (
                await connection.execute(
                    text(
                        "INSERT INTO conversations (org_id, title) VALUES (:org, 'Metered') "
                        "RETURNING id"
                    ),
                    {"org": org_id},
                )
            ).scalar_one()
            await connection.execute(
                text(
                    "INSERT INTO agent_runs (id, org_id, conversation_id, status, question) "
                    "VALUES (:id, :org, :conversation, 'running', 'How much did that cost?')"
                ),
                {"id": run_id, "org": org_id, "conversation": conversation_id},
            )
    finally:
        await engine.dispose()
    return run_id
