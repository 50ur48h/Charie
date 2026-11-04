"""Conversations, messages and the life of a run (architecture Part 10.1 and 10.2)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Final, cast

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from charie.db.models import (
    AgentRun,
    Conversation,
    DataSource,
    Finding,
    Message,
    Organization,
    QueryExecution,
    ResultArtifact,
    UsageLedger,
)
from charie.runs.events import EventType, RecordedEvent, read_events, write_event
from charie.tenancy.session import org_session

__all__ = [
    "ConversationView",
    "ExecutionView",
    "InvalidTransitionError",
    "MessageView",
    "NotFoundError",
    "PriorTurn",
    "RunView",
    "add_finding",
    "conversation_history",
    "create_conversation",
    "get_conversation",
    "get_execution",
    "get_run",
    "list_conversations",
    "list_events",
    "list_messages",
    "post_message",
    "record_answer",
    "transition",
]

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_VALIDATING = "validating"
STATUS_COMPLETED = "completed"
STATUS_INTERRUPTED = "interrupted"
STATUS_FAILED = "failed"
STATUS_BUDGET_EXHAUSTED = "budget_exhausted"

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

#: Where a run may go from where it is.
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATUS_QUEUED: (STATUS_RUNNING, STATUS_INTERRUPTED, STATUS_FAILED),
    STATUS_RUNNING: (
        STATUS_VALIDATING,
        STATUS_COMPLETED,
        STATUS_INTERRUPTED,
        STATUS_FAILED,
        STATUS_BUDGET_EXHAUSTED,
    ),
    # Back to running is the critic's bounded re-entry (arch M9, Phase 9).
    STATUS_VALIDATING: (
        STATUS_RUNNING,
        STATUS_COMPLETED,
        STATUS_INTERRUPTED,
        STATUS_FAILED,
        STATUS_BUDGET_EXHAUSTED,
    ),
}

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {STATUS_COMPLETED, STATUS_INTERRUPTED, STATUS_FAILED, STATUS_BUDGET_EXHAUSTED}
)

#: How much of a question becomes a conversation's title when the client did not give one.
TITLE_LENGTH = 120


class NotFoundError(Exception):
    """No such object for this caller."""


class InvalidTransitionError(Exception):
    """A run cannot go from where it is to where it was asked to go."""


@dataclass(frozen=True, slots=True)
class ConversationView:
    id: uuid.UUID
    title: str | None
    user_id: uuid.UUID | None
    created_at: datetime
    message_count: int = 0
    last_run_id: uuid.UUID | None = None
    #: The data source every question here is answered against, if one was named.
    data_source_id: uuid.UUID | None = None
    #: That source's display name, so a client can say which database it is talking to without a...
    data_source_name: str | None = None
    #: When this thread was put away, or None while it is in the list (D-039).
    archived_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MessageView:
    id: uuid.UUID
    role: str
    content: str
    run_id: uuid.UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PriorTurn:
    """An earlier question in this thread, and what it was answered with."""

    run_id: uuid.UUID
    question: str
    answer: str | None


@dataclass(frozen=True, slots=True)
class FindingView:
    id: uuid.UUID
    statement: str
    #: ``query_executions.id`` values — the citation an answer is walked back through.
    support: list[str]
    confidence: str
    #: True when the composed answer rests on this finding (WP9.2).
    cited: bool = False


#: The budget dimensions a waiting person is shown.
PROGRESS_DIMENSIONS: Final = ("iterations", "queries", "wall_seconds")


def _progress_of(budget: dict[str, object] | None) -> dict[str, object]:
    """How far through its allowance a run is, as counters and ceilings."""
    if not budget:
        return {}
    limits = budget.get("limits")
    ceilings = cast(dict[str, object], limits) if isinstance(limits, dict) else {}
    used: dict[str, object] = {}
    allowed: dict[str, object] = {}
    for name in PROGRESS_DIMENSIONS:
        # `elapsed_seconds` is what the loop calls the wall clock it has spent.
        key = "elapsed_seconds" if name == "wall_seconds" else name
        if key in budget:
            used[name] = budget[key]
        if name in ceilings:
            allowed[name] = ceilings[name]
    return {"used": used, "limits": allowed} if used or allowed else {}


@dataclass(frozen=True, slots=True)
class RunView:
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    question: str
    #: The assistant's message for this run, once there is one.
    answer: str | None
    findings: list[FindingView] = field(default_factory=list["FindingView"])
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failure_reason: str | None = None
    cost_estimate: Decimal | None = None
    model_usage: dict[str, object] = field(default_factory=dict[str, object])
    #: How far through its allowance this run is — the counters and the ceilings together.
    progress: dict[str, object] = field(default_factory=dict[str, object])
    #: What this answer does not establish.
    limitations: list[str] = field(default_factory=list[str])
    #: One line on how the answer was reached, for a reader who will not open the SQL.
    method: str = ""
    #: Which semantic definitions governed this answer, and how many there were to match (B-087).
    definitions_applied: list[str] = field(default_factory=list[str])
    definitions_available: int = 0
    #: `answered` | `partly` | `refused` (D-044).
    state: str | None = None
    #: What the run could not answer, in the composer's words.
    unanswered: str = ""
    #: The chart this answer carries, or the reason it carries none (WP11.1).
    chart: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ExecutionView:
    """One query a run ran, as a person may see it (architecture 10.2)."""

    id: uuid.UUID
    run_id: uuid.UUID
    #: ok | error | refused. A refusal never reached an engine.
    status: str
    sql: str
    tables: list[str]
    columns: list[str]
    row_count: int | None
    duration_ms: int | None
    violation_code: str | None
    #: Sanitized already — connectors raise nothing else.
    error: str | None
    sensitive_accessed: bool
    masked_columns: list[str]
    sample_rows: list[list[object]]
    truncated: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AskResult:
    """What ``POST …/messages`` answers with."""

    run_id: uuid.UUID
    message_id: uuid.UUID
    #: False when an idempotency key matched and this is the run that already existed.
    created: bool
    #: The conversation's data source.
    data_source_id: uuid.UUID | None = None


# --- Conversations ---


async def _owned_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> Conversation:
    """The caller's own conversation, or ``NotFoundError``."""
    row = (
        (await session.execute(select(Conversation).where(Conversation.id == conversation_id)))
        .scalars()
        .one_or_none()
    )
    if row is None or row.user_id is None or row.user_id != user_id:
        raise NotFoundError("No such conversation")
    return row


async def _named_data_source(
    session: AsyncSession, data_source_id: uuid.UUID | None
) -> DataSource | None:
    """The organization's own data source with that id, or ``NotFoundError``."""
    if data_source_id is None:
        return None
    row = (
        (await session.execute(select(DataSource).where(DataSource.id == data_source_id)))
        .scalars()
        .one_or_none()
    )
    if row is None:
        raise NotFoundError("No such data source")
    return row


async def create_conversation(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str | None = None,
    data_source_id: uuid.UUID | None = None,
) -> ConversationView:
    """Start a thread, stamped with the database it will be about."""
    async with org_session(org_id) as session:
        if data_source_id is None:
            data_source_id = (
                await session.execute(
                    select(Organization.active_data_source_id).where(Organization.id == org_id)
                )
            ).scalar_one_or_none()
        source = await _named_data_source(session, data_source_id)
        row = Conversation(
            org_id=org_id, user_id=user_id, title=title, data_source_id=data_source_id
        )
        session.add(row)
        await session.flush()
        return ConversationView(
            id=row.id,
            title=row.title,
            user_id=row.user_id,
            created_at=row.created_at,
            data_source_id=row.data_source_id,
            data_source_name=source.name if source is not None else None,
        )


async def list_conversations(
    *, org_id: uuid.UUID, user_id: uuid.UUID, archived: bool = False
) -> list[ConversationView]:
    """This caller's conversations, newest first, with enough to render a list."""
    async with org_session(org_id) as session:
        counts = (
            select(Message.conversation_id, func.count(Message.id).label("message_count"))
            .group_by(Message.conversation_id)
            .subquery()
        )
        rows = await session.execute(
            select(Conversation, func.coalesce(counts.c.message_count, 0), DataSource.name)
            .outerjoin(counts, counts.c.conversation_id == Conversation.id)
            .outerjoin(DataSource, DataSource.id == Conversation.data_source_id)
            .where(Conversation.user_id == user_id)
            .where(
                Conversation.archived_at.is_not(None)
                if archived
                else Conversation.archived_at.is_(None)
            )
            .order_by(Conversation.created_at.desc())
        )
        return [
            ConversationView(
                id=conversation.id,
                title=conversation.title,
                user_id=conversation.user_id,
                created_at=conversation.created_at,
                message_count=count,
                data_source_id=conversation.data_source_id,
                data_source_name=source_name,
                archived_at=conversation.archived_at,
            )
            for conversation, count, source_name in rows.all()
        ]


async def rename_conversation(
    *, org_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID, title: str
) -> ConversationView:
    """Give a thread a name its owner will recognise later (plan WP11.2)."""
    cleaned = title.strip()
    async with org_session(org_id) as session:
        row = await _owned_conversation(session, conversation_id=conversation_id, user_id=user_id)
        row.title = cleaned or None
        await session.flush()
    return await get_conversation(org_id=org_id, user_id=user_id, conversation_id=conversation_id)


async def set_conversation_archived(
    *, org_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID, archived: bool
) -> ConversationView:
    """Put a thread away, or bring it back (D-039)."""
    async with org_session(org_id) as session:
        row = await _owned_conversation(session, conversation_id=conversation_id, user_id=user_id)
        if archived and row.archived_at is None:
            row.archived_at = datetime.now(UTC)
        elif not archived:
            row.archived_at = None
        await session.flush()
    return await get_conversation(org_id=org_id, user_id=user_id, conversation_id=conversation_id)


async def get_conversation(
    *, org_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> ConversationView:
    async with org_session(org_id) as session:
        row = await _owned_conversation(session, conversation_id=conversation_id, user_id=user_id)
        latest = (
            await session.execute(
                select(AgentRun.id)
                .where(AgentRun.conversation_id == conversation_id)
                .order_by(AgentRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        count = (
            await session.execute(
                select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
            )
        ).scalar_one()
        source_name = (
            await session.execute(
                select(DataSource.name).where(DataSource.id == row.data_source_id)
            )
        ).scalar_one_or_none()
        return ConversationView(
            id=row.id,
            title=row.title,
            user_id=row.user_id,
            created_at=row.created_at,
            message_count=count,
            last_run_id=latest,
            data_source_id=row.data_source_id,
            data_source_name=source_name,
            archived_at=row.archived_at,
        )


async def list_messages(
    *, org_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[MessageView]:
    async with org_session(org_id) as session:
        await _owned_conversation(session, conversation_id=conversation_id, user_id=user_id)
        rows = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at, Message.id)
                )
            )
            .scalars()
            .all()
        )
        return [
            MessageView(
                id=row.id,
                role=row.role,
                content=row.content,
                run_id=row.run_id,
                created_at=row.created_at,
            )
            for row in rows
        ]


# --- Asking a question ---


async def post_message(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    content: str,
    idempotency_key: str,
) -> AskResult:
    """Record a question and queue the run that will answer it."""
    try:
        return await _create_question(
            org_id=org_id,
            user_id=user_id,
            conversation_id=conversation_id,
            content=content,
            idempotency_key=idempotency_key,
        )
    except IntegrityError:
        # Two identical POSTs in flight at once: the unique index refused the second.
        existing = await _find_by_key(
            org_id=org_id,
            user_id=user_id,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
        )
        if existing is None:  # pragma: no cover - a different constraint, not ours
            raise
        return existing


async def _create_question(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    content: str,
    idempotency_key: str,
) -> AskResult:
    async with org_session(org_id) as session:
        conversation = await _owned_conversation(
            session, conversation_id=conversation_id, user_id=user_id
        )

        replayed = (
            (
                await session.execute(
                    select(Message).where(
                        Message.conversation_id == conversation_id,
                        Message.idempotency_key == idempotency_key,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if replayed is not None:
            # The run this message already started.
            if replayed.run_id is None:  # pragma: no cover - only after a run is deleted
                raise NotFoundError("That message's run no longer exists")
            return AskResult(
                run_id=replayed.run_id,
                message_id=replayed.id,
                created=False,
                data_source_id=conversation.data_source_id,
            )

        run = AgentRun(
            org_id=org_id,
            conversation_id=conversation_id,
            user_id=user_id,
            status=STATUS_QUEUED,
            question=content,
        )
        session.add(run)
        await session.flush()

        message = Message(
            org_id=org_id,
            conversation_id=conversation_id,
            role=ROLE_USER,
            content=content,
            run_id=run.id,
            idempotency_key=idempotency_key,
        )
        session.add(message)

        # A conversation nobody titled is a blank line in a list.
        if conversation.title is None:
            conversation.title = _title_from(content)

        await session.flush()
        return AskResult(
            run_id=run.id,
            message_id=message.id,
            created=True,
            data_source_id=conversation.data_source_id,
        )


async def _find_by_key(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    idempotency_key: str,
) -> AskResult | None:
    async with org_session(org_id) as session:
        conversation = await _owned_conversation(
            session, conversation_id=conversation_id, user_id=user_id
        )
        row = (
            (
                await session.execute(
                    select(Message).where(
                        Message.conversation_id == conversation_id,
                        Message.idempotency_key == idempotency_key,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None or row.run_id is None:
            return None
        return AskResult(
            run_id=row.run_id,
            message_id=row.id,
            created=False,
            data_source_id=conversation.data_source_id,
        )


def _title_from(question: str) -> str:
    collapsed = " ".join(question.split())
    if len(collapsed) <= TITLE_LENGTH:
        return collapsed
    return collapsed[: TITLE_LENGTH - 1].rstrip() + "…"


# --- The life of a run ---


async def _owned_run(
    session: AsyncSession, *, run_id: uuid.UUID, user_id: uuid.UUID | None
) -> AgentRun:
    """The run, and — when a user is given — a check that it is theirs."""
    row = (
        (await session.execute(select(AgentRun).where(AgentRun.id == run_id)))
        .scalars()
        .one_or_none()
    )
    if row is None:
        raise NotFoundError("No such run")
    if user_id is not None and row.user_id != user_id:
        raise NotFoundError("No such run")
    return row


async def _run_view(session: AsyncSession, run: AgentRun) -> RunView:
    """A run with its answer and its findings — what 10.2 promises this route returns."""
    answer = (
        await session.execute(
            select(Message.content)
            .where(Message.run_id == run.id, Message.role == ROLE_ASSISTANT)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    findings = (
        (
            await session.execute(
                select(Finding)
                .where(Finding.run_id == run.id)
                .order_by(Finding.created_at, Finding.id)
            )
        )
        .scalars()
        .all()
    )
    grounding = _grounding(run.state)
    return RunView(
        id=run.id,
        conversation_id=run.conversation_id,
        status=run.status,
        question=run.question,
        answer=answer,
        findings=[
            FindingView(
                id=finding.id,
                statement=finding.statement,
                support=[str(item) for item in finding.support],
                confidence=finding.confidence,
                cited=finding.cited,
            )
            for finding in findings
        ],
        state=run.outcome_state,
        unanswered=run.unanswered or "",
        started_at=run.started_at,
        finished_at=run.finished_at,
        failure_reason=run.failure_reason,
        cost_estimate=run.cost_estimate,
        progress=_progress_of(run.budget),
        model_usage=dict(run.model_usage),
        limitations=[str(note) for note in run.limitations],
        method=run.method or "",
        chart=dict(run.chart) if run.chart else None,
        # Read off the run's own persisted state rather than recomputed.
        definitions_applied=grounding[0],
        definitions_available=grounding[1],
    )


def _grounding(state: object) -> tuple[list[str], int]:
    """The definitions a run applied, and how many it could have (B-087)."""
    if not isinstance(state, dict):
        return [], 0
    stored = cast("dict[str, object]", state)
    applied = stored.get("applied_definitions")
    available = stored.get("definitions_available")
    names = (
        [str(name) for name in cast("list[object]", applied)] if isinstance(applied, list) else []
    )
    return names, available if isinstance(available, int) else 0


async def get_run(
    *, org_id: uuid.UUID, run_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> RunView:
    async with org_session(org_id) as session:
        return await _run_view(session, await _owned_run(session, run_id=run_id, user_id=user_id))


async def list_conversation_runs(
    *, org_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[RunView]:
    """Every run in this thread, oldest first (B-106)."""
    async with org_session(org_id) as session:
        await _owned_conversation(session, conversation_id=conversation_id, user_id=user_id)
        rows = (
            (
                await session.execute(
                    select(AgentRun)
                    # `(created_at, id)` as a pair, for the reason `conversation_history` gives.
                    .where(AgentRun.conversation_id == conversation_id)
                    .order_by(AgentRun.created_at, AgentRun.id)
                )
            )
            .scalars()
            .all()
        )
        return [await _run_view(session, row) for row in rows]


async def conversation_history(
    *, org_id: uuid.UUID, run_id: uuid.UUID, turns: int
) -> list[PriorTurn]:
    """The turns this run follows, oldest first, capped at ``turns``."""
    if turns <= 0:
        return []

    async with org_session(org_id) as session:
        run = await _owned_run(session, run_id=run_id, user_id=None)
        earlier = (
            (
                await session.execute(
                    select(AgentRun)
                    .where(
                        AgentRun.conversation_id == run.conversation_id,
                        or_(
                            AgentRun.created_at < run.created_at,
                            and_(
                                AgentRun.created_at == run.created_at,
                                AgentRun.id < run.id,
                            ),
                        ),
                    )
                    .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
                    .limit(turns)
                )
            )
            .scalars()
            .all()
        )
        if not earlier:
            return []

        # Ascending, so a run that composed twice — the critic's one re-entry.
        replies = (
            await session.execute(
                select(Message.run_id, Message.content)
                .where(
                    Message.run_id.in_([row.id for row in earlier]),
                    Message.role == ROLE_ASSISTANT,
                )
                .order_by(Message.created_at, Message.id)
            )
        ).all()
        answers: dict[uuid.UUID, str] = {}
        for reply_run_id, content in replies:
            if reply_run_id is not None:
                answers[reply_run_id] = content
        return [
            PriorTurn(run_id=row.id, question=row.question, answer=answers.get(row.id))
            for row in reversed(earlier)
        ]


async def _roll_up_usage(session: AsyncSession, run: AgentRun) -> None:
    """Fill ``cost_estimate`` and ``model_usage`` from this run's ledger rows."""
    rows = (
        await session.execute(
            select(
                UsageLedger.model,
                UsageLedger.role,
                func.count().label("calls"),
                func.coalesce(func.sum(UsageLedger.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(UsageLedger.output_tokens), 0).label("output_tokens"),
                func.sum(UsageLedger.cost_usd).label("cost_usd"),
                func.count().filter(UsageLedger.cost_usd.is_(None)).label("unpriced"),
                # Cached input is summed over the rows that reported one.
                func.sum(UsageLedger.cached_input_tokens).label("cached_input_tokens"),
                func.count()
                .filter(UsageLedger.cached_input_tokens.isnot(None))
                .label("cached_reported"),
                func.count().filter(UsageLedger.tokens_estimated.is_(True)).label("estimated"),
            )
            .where(UsageLedger.run_id == run.id)
            .group_by(UsageLedger.model, UsageLedger.role)
            .order_by(UsageLedger.model, UsageLedger.role)
        )
    ).all()

    by_model: list[dict[str, object]] = []
    calls = inputs = outputs = unpriced = 0
    cached = cached_reported = estimated = 0
    total = Decimal("0")
    for row in rows:
        calls += row.calls
        inputs += int(row.input_tokens)
        outputs += int(row.output_tokens)
        unpriced += row.unpriced
        cached += int(row.cached_input_tokens or 0)
        cached_reported += row.cached_reported
        estimated += row.estimated
        if row.cost_usd is not None:
            total += row.cost_usd
        by_model.append(
            {
                "model": row.model,
                "role": row.role,
                "calls": row.calls,
                "input_tokens": int(row.input_tokens),
                "output_tokens": int(row.output_tokens),
                "cached_input_tokens": (
                    None if row.cached_reported == 0 else int(row.cached_input_tokens or 0)
                ),
                "estimated_calls": row.estimated,
                # A string, because JSONB has no decimal and a float would round a price.
                "cost_usd": None if row.cost_usd is None else str(row.cost_usd),
            }
        )

    run.model_usage = {
        "calls": calls,
        "input_tokens": inputs,
        "output_tokens": outputs,
        # Recorded, not discounted (revision 0034).
        "cached_input_tokens": None if cached_reported == 0 else cached,
        "unpriced_calls": unpriced,
        # How many of these calls were counted by us rather than by the provider.
        "estimated_calls": estimated,
        "by_model": by_model,
    }
    run.cost_estimate = None if (unpriced or not rows) else total


async def transition(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    status: str,
    failure_reason: str | None = None,
    state: str | None = None,
    unanswered: str = "",
    totals: dict[str, object] | None = None,
) -> RunView:
    """Move a run, and write the event that says so."""
    async with org_session(org_id) as session:
        run = await _owned_run(session, run_id=run_id, user_id=None)
        allowed = ALLOWED_TRANSITIONS.get(run.status, ())
        if status not in allowed:
            raise InvalidTransitionError(
                f"A run that is {run.status} cannot become {status}"
                + (f"; it may become {' or '.join(allowed)}" if allowed else " — it has finished")
            )

        # Read before the write, because "is this the first time it started" cannot be asked...
        first_start = status == STATUS_RUNNING and run.started_at is None

        now = datetime.now(UTC)
        run.status = status
        if first_start:
            run.started_at = now
        if status in TERMINAL_STATUSES:
            run.finished_at = now
            run.failure_reason = failure_reason
            # Recorded beside `failure_reason` because it is the same kind of fact.
            run.outcome_state = state
            # Empty becomes NULL, because the CHECK that makes `partly` impossible without a...
            run.unanswered = unanswered or None
            # Written at the ending, for the same reason `outcome_state` is.
            await _roll_up_usage(session, run)
        await session.flush()

        event, payload = _event_for(status, run=run, totals=totals, first_start=first_start)
        if event is not None:
            await write_event(
                session, org_id=org_id, run_id=run_id, event_type=event, payload=payload
            )

        return await _run_view(session, run)


def _event_for(
    status: str, *, run: AgentRun, totals: dict[str, object] | None, first_start: bool
) -> tuple[EventType | None, dict[str, object]]:
    """The trace entry a status change earns, per architecture 10.3's type list."""
    if first_start:
        return ("run_started", {"question": run.question})
    if status in TERMINAL_STATUSES:
        payload: dict[str, object] = {"status": status, "totals": totals or {}}
        if run.failure_reason is not None:
            payload["reason"] = run.failure_reason
        return ("run_finished", payload)
    return (None, {})


def _chart_outcome(chart: Mapping[str, object] | None) -> str | None:
    """What the trace says happened to the chart: nothing, a spec, or which rule refused it."""
    if chart is None:
        return None
    if chart.get("spec") is not None:
        return "spec"
    code = chart.get("code")
    return str(code) if code else "declined"


async def record_answer(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    content: str,
    limitations: Sequence[str] = (),
    chart: Mapping[str, object] | None = None,
    method: str = "",
    coverage: Mapping[str, object] | None = None,
) -> MessageView:
    """Write the assistant's reply for a run, and what it does not establish."""
    async with org_session(org_id) as session:
        run = await _owned_run(session, run_id=run_id, user_id=None)
        message = Message(
            org_id=org_id,
            conversation_id=run.conversation_id,
            role=ROLE_ASSISTANT,
            content=content,
            run_id=run_id,
        )
        session.add(message)
        run.limitations = list(limitations)
        if method:
            run.method = method
        if chart is not None:
            run.chart = dict(chart)
        await session.flush()
        await write_event(
            session,
            org_id=org_id,
            run_id=run_id,
            event_type="answer_composed",
            payload={
                "message_id": str(message.id),
                "length": len(content),
                "limitations": len(limitations),
                # Both outcomes are in the trace.
                "chart": _chart_outcome(chart),
                # Present whatever it says, including "I could not look." A run where the period...
                "coverage": dict(coverage) if coverage is not None else None,
            },
        )
        return MessageView(
            id=message.id,
            role=message.role,
            content=message.content,
            run_id=run_id,
            created_at=message.created_at,
        )


async def mark_cited(
    *, org_id: uuid.UUID, run_id: uuid.UUID, executions: Sequence[uuid.UUID | str]
) -> int:
    """Mark the findings this run's answer rests on, and return how many."""
    wanted = {str(execution) for execution in executions}
    if not wanted:
        return 0

    async with org_session(org_id) as session:
        rows = (
            (await session.execute(select(Finding).where(Finding.run_id == run_id))).scalars().all()
        )
        marked = 0
        for finding in rows:
            cited = bool(wanted.intersection(str(item) for item in finding.support))
            if finding.cited != cited:
                finding.cited = cited
            marked += int(cited)
        return marked


async def add_finding(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    statement: str,
    support: Sequence[uuid.UUID | str] = (),
    confidence: str = "medium",
) -> FindingView:
    """Record something the run concluded, and say so in the trace."""
    async with org_session(org_id) as session:
        await _owned_run(session, run_id=run_id, user_id=None)
        row = Finding(
            org_id=org_id,
            run_id=run_id,
            statement=statement,
            support=[str(item) for item in support],
            confidence=confidence,
        )
        session.add(row)
        await session.flush()
        await write_event(
            session,
            org_id=org_id,
            run_id=run_id,
            event_type="finding_added",
            payload={
                "statement": statement,
                "support": [str(item) for item in support],
                "confidence": confidence,
            },
        )
        return FindingView(
            id=row.id,
            statement=row.statement,
            support=[str(item) for item in row.support],
            confidence=row.confidence,
        )


async def list_events(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    after: int = 0,
) -> list[RecordedEvent]:
    """This run's trace after ``seq``, once the caller is shown to own the run."""
    async with org_session(org_id) as session:
        await _owned_run(session, run_id=run_id, user_id=user_id)
    return await read_events(org_id=org_id, run_id=run_id, after=after)


# --- Resolving a citation (architecture 10.2, B-034) ---


async def get_execution(
    *,
    org_id: uuid.UUID,
    run_id: uuid.UUID,
    execution_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> ExecutionView:
    """One query this run ran: its statement, its shape, and its masked rows."""
    async with org_session(org_id) as session:
        await _owned_run(session, run_id=run_id, user_id=user_id)
        row = (
            (
                await session.execute(
                    select(QueryExecution).where(
                        QueryExecution.id == execution_id,
                        QueryExecution.run_id == run_id,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if row is None:
            raise NotFoundError("No such execution on this run")

        artifact = (
            (
                await session.execute(
                    select(ResultArtifact).where(ResultArtifact.query_execution_id == row.id)
                )
            )
            .scalars()
            .one_or_none()
        )
        summary: dict[str, object] = dict(artifact.summary) if artifact is not None else {}
        return ExecutionView(
            id=row.id,
            run_id=run_id,
            status=row.status,
            sql=row.sql_text,
            tables=[str(table) for table in row.tables],
            columns=_string_list(summary.get("columns")),
            row_count=row.row_count,
            duration_ms=row.duration_ms,
            violation_code=row.violation_code,
            error=row.error,
            sensitive_accessed=row.sensitive_accessed,
            masked_columns=_string_list(summary.get("masked_columns")),
            sample_rows=[list(sample) for sample in artifact.sample_rows]
            if artifact is not None
            else [],
            truncated=bool(artifact.truncated) if artifact is not None else False,
            created_at=row.created_at,
        )


def _string_list(value: object) -> list[str]:
    """A JSONB list, as strings — and anything else as nothing."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast("list[object]", value)]
