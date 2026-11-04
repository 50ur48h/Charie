"""One real question, end to end, against a real model."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "src"))

from charie.agent.runner import execute_run  # noqa: E402
from charie.datasources import service as datasources  # noqa: E402
from charie.runs import service as runs  # noqa: E402
from charie.runs.events import read_events  # noqa: E402
from charie.tenancy.session import org_session  # noqa: E402

DEFAULT_QUESTION = "How many orders were placed in July 2026?"


async def _resolve_source(org_id: uuid.UUID, name: str | None) -> uuid.UUID:
    sources = await datasources.list_data_sources(org_id)
    if not sources:
        raise SystemExit("This organization has no data sources registered.")
    if name is None:
        if len(sources) == 1:
            return sources[0].id
        listed = ", ".join(source.name for source in sources)
        raise SystemExit(f"More than one data source; pass --source with one of: {listed}")
    for source in sources:
        if source.name == name:
            return source.id
    listed = ", ".join(source.name for source in sources)
    raise SystemExit(f"No data source named {name!r}. There is: {listed}")


async def _first_user(org_id: uuid.UUID) -> uuid.UUID:
    """Any member, to own the conversation."""
    async with org_session(org_id) as session:
        found = (
            await session.execute(
                text("SELECT user_id FROM org_memberships WHERE org_id = :org LIMIT 1"),
                {"org": org_id},
            )
        ).scalar_one_or_none()
    if found is None:
        raise SystemExit("This organization has no members.")
    return uuid.UUID(str(found))


async def _ask(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    data_source_id: uuid.UUID,
    question: str,
) -> int:
    """One question in an existing thread, run to its ending and printed."""
    asked = await runs.post_message(
        org_id=org_id,
        user_id=user_id,
        conversation_id=conversation_id,
        content=question,
        idempotency_key=uuid.uuid4().hex,
    )

    print(f"  run       {asked.run_id}")
    print(f"  question  {question}\n")

    outcome = await execute_run(
        org_id=org_id,
        run_id=asked.run_id,
        data_source_id=data_source_id,
        actor_user_id=user_id,
    )

    print(f"  status    {outcome.status}")
    print(f"  answered  {outcome.answered}")
    # `repaired` retired with the single-shot runner: a correction is now just the next iteration.
    print(f"  iterations{outcome.iterations:>3}")
    print(f"  stopped   {outcome.stopped_by or '-'}")
    print(f"  llm calls {outcome.llm_calls}")
    print(f"\n  {outcome.answer}\n")

    # The trace, because "it answered" and "it can show its working" are different claims and...
    print("  trace:")
    for event in await read_events(org_id=org_id, run_id=asked.run_id):
        extra = ""
        if event.type == "context_selected":
            extra = (
                f"  history_turns {event.payload.get('history_turns')}"
                f"  tables via {event.payload.get('tables_found_via')}"
                f"  {event.payload.get('tables')}"
            )
        print(f"    {event.seq:>2}  {event.type}{extra}")

    view = await runs.get_run(org_id=org_id, run_id=asked.run_id)
    for finding in view.findings:
        print(f"\n  finding   {finding.statement}")
        print(f"  cites     {', '.join(finding.support) or '(nothing)'}")

    # A citation that resolves is the difference between evidence and decoration.
    async with org_session(org_id) as session:
        for execution_id in outcome.execution_ids:
            row = (
                await session.execute(
                    text(
                        "SELECT status, row_count, left(sql_text, 90) AS sql "
                        "FROM query_executions WHERE id = :id"
                    ),
                    {"id": execution_id},
                )
            ).one()
            print(f"\n  execution {execution_id}")
            print(f"    status  {row.status}  rows {row.row_count}")
            print(f"    sql     {row.sql}")

    return 0 if outcome.status == "completed" else 1


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="Organization id to ask within")
    parser.add_argument("--source", default=None, help="Data source name (required if >1)")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument(
        "--then",
        action="append",
        default=[],
        metavar="QUESTION",
        help=(
            "A follow-up asked in the same conversation, repeatable. This is what "
            "proves D-029: 'check again' is meaningless unless the run is given "
            "the turn it follows."
        ),
    )
    args = parser.parse_args()

    org_id = uuid.UUID(args.org)
    data_source_id = await _resolve_source(org_id, args.source)
    user_id = await _first_user(org_id)

    conversation = await runs.create_conversation(
        org_id=org_id, user_id=user_id, title="Agent smoke"
    )
    print(f"  org       {org_id}")
    print(f"  thread    {conversation.id}\n")

    # Sequential and never concurrent.
    code = await _ask(
        org_id=org_id,
        user_id=user_id,
        conversation_id=conversation.id,
        data_source_id=data_source_id,
        question=args.question,
    )
    for follow_up in args.then:
        print("\n  ---\n")
        code |= await _ask(
            org_id=org_id,
            user_id=user_id,
            conversation_id=conversation.id,
            data_source_id=data_source_id,
            question=follow_up,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
