"""Live smoke against a real provider."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path
from typing import get_args

from pydantic import BaseModel, Field
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "src"))

from charie.config import get_settings  # noqa: E402
from charie.llm import registry, service  # noqa: E402
from charie.llm.base import CallLimits, LLMRequest, Message, Role, Tags  # noqa: E402
from charie.tenancy.session import org_session  # noqa: E402


class Verdict(BaseModel):
    """A deliberately tiny schema: enough to prove structured output round-trips."""

    kind: str = Field(description="One of: data_question, definition, smalltalk")
    confident: bool = Field(description="Whether the classification is clear-cut")


QUESTION = "How many pizza orders were placed in July?"
MESSAGES = [
    Message(role="system", content="You classify questions for a data analysis tool."),
    Message(role="user", content=f"Classify this question: {QUESTION}"),
]


async def _first_org() -> uuid.UUID | None:
    """Any organization to attribute the call to — the ledger is tenant-scoped."""
    from charie.db.engine import build_engine

    engine = build_engine(url=get_settings().require_database_url())
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT id FROM organizations ORDER BY created_at LIMIT 1")
                )
            ).first()
            return None if row is None else uuid.UUID(str(row[0]))
    finally:
        await engine.dispose()


async def direct(role: Role) -> int:
    """One provider call, no database, no metering."""
    settings = get_settings()
    chain = registry.resolve(role, settings)
    choice = chain[0]
    provider = registry.get_provider(choice.provider, settings)
    print(f"  provider {choice.provider}, tier {choice.tier}, model {choice.model}")

    completion = await provider.complete(
        LLMRequest(
            model=choice.model,
            messages=MESSAGES,
            tags=Tags(org_id=uuid.uuid4(), role=role),
            schema=Verdict,
            limits=CallLimits(max_output_tokens=200),
        )
    )
    print(f"  text     {completion.text[:200]!r}")
    print(f"  usage    in={completion.usage.input_tokens} out={completion.usage.output_tokens}")
    print(f"  finish   {completion.finish_reason}")
    print("\n  NOTE: --direct proves the wire shape only. Nothing was metered.")
    await provider.aclose()
    return 0


async def through_front_door(role: Role) -> int:
    """The whole path: resolve, cap, call, meter, parse, then read the rows back."""
    settings = get_settings()
    org_id = await _first_org()
    if org_id is None:
        print("  no organization in the platform database — run `make up` and sign in once,")
        print("  or use --direct to skip the database.")
        return 1

    run_id = uuid.uuid4()
    chain = registry.resolve(role, settings)
    print(f"  org      {org_id}")
    print(f"  run      {run_id}")
    print(f"  chain    {' -> '.join(f'{c.provider}:{c.model}' for c in chain)}")
    if settings.llm_run_cost_limit_usd is not None:
        print(f"  ceiling  ${settings.llm_run_cost_limit_usd:.2f} for this run")

    completion = await service.complete(
        role=role,
        org_id=org_id,
        messages=MESSAGES,
        schema=Verdict,
        run_id=run_id,
        limits=CallLimits(max_output_tokens=200),
        settings=settings,
    )
    verdict = completion.parsed_as(Verdict)
    print(f"\n  parsed   kind={verdict.kind!r} confident={verdict.confident}")
    print(f"  served   {completion.provider}:{completion.model} in {completion.latency_ms} ms")
    print(f"  repaired {completion.repaired}")

    async with org_session(org_id) as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT role, tier, provider, model, status, input_tokens, "
                        "output_tokens, cost_usd, repaired, error FROM usage_ledger "
                        "WHERE run_id = :run ORDER BY created_at, id"
                    ),
                    {"run": run_id},
                )
            )
            .mappings()
            .all()
        )

    print(f"\n  usage_ledger rows for this run ({len(rows)}):")
    for row in rows:
        print(f"    {dict(row)}")
    if not rows:
        print("    NONE — a call was made and nothing was recorded. That is a bug.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", default="intake", choices=list(get_args(Role)))
    parser.add_argument(
        "--direct",
        action="store_true",
        help="call the provider without the platform database or the meter",
    )
    args = parser.parse_args()
    role: Role = args.role

    settings = get_settings()
    print(f"providers: {list(settings.llm_providers)}")
    print(f"role     : {role}\n")
    if not settings.llm_models:
        print("LLM_MODELS is empty — nothing can be resolved. See .env.example.")
        return 1

    runner = direct if args.direct else through_front_door
    return asyncio.run(runner(role))


if __name__ == "__main__":
    sys.exit(main())
