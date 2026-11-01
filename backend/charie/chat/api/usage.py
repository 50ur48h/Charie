"""`GET /api/usage?month=YYYY-MM`: the month's AI cost, from `ai_calls`."""

import calendar
import re
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.shared.ai.spending import as_utc, month_spent, month_window, spending_state
from charie.shared.db import get_session
from charie.shared.errors import ApiError
from charie.shared.settings import get_setting
from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.usage import AiCall

usage_router = APIRouter()

# The design's "Where the money goes" (exact job names from the AI layer).
JOB_GROUPS: dict[str, tuple[str, ...]] = {
    "Planning and judging": ("understand_question", "plan_round", "check_enough"),
    "Data helpers": ("write_sql",),
    "Document search": ("find_quotes",),
    "Writing answers": ("write_answer", "extract_memories", "name_chat"),
    "Reviewing answers": ("review_answer",),
}
_JOB_TO_GROUP = {job: group for group, names in JOB_GROUPS.items() for job in names}


def group_for(job: str, app: str) -> str:
    """Learning and Tests win by app; the rest by job name."""
    if app == "learner":
        return "Learning"
    if app == "tests":
        return "Tests"
    return _JOB_TO_GROUP.get(job, "Other")


def parse_month(raw: str | None, time_zone: str | None, now: datetime) -> str:
    """`YYYY-MM`, defaulting to this month in the owner's time zone."""
    if raw is None:
        zone = ZoneInfo(time_zone) if time_zone else UTC
        return now.astimezone(zone).strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", raw):
        raise ApiError(400, "bad_month", "Month must look like 2026-10.")
    return raw


class UsageTotals(BaseModel):
    count: int
    cost_usd: float


class UsageDay(BaseModel):
    date: str
    questions_usd: float
    learning_usd: float
    tests_usd: float


class UsageGroup(BaseModel):
    group: str
    cost_usd: float
    percent: float


class TopQuestion(BaseModel):
    message_id: int
    chat_id: int
    question: str
    asked_at: str
    seconds: int
    steps: int
    cost_usd: float


class UsageSummary(BaseModel):
    month: str
    days_in_month: int
    resets_on: str
    spent_usd: float
    limit_usd: float
    warn_percent: float
    percent_used: float
    state: str
    expected_usd: float
    questions: UsageTotals
    learning_runs: UsageTotals
    per_day: list[UsageDay]
    per_group: list[UsageGroup]
    top_questions: list[TopQuestion]


def money(value: Decimal | float | int) -> float:
    """Money goes out as JSON numbers rounded to 4 decimals."""
    return round(float(value), 4)


def build_usage(
    session: Session, month: str, time_zone: str | None, now: datetime
) -> dict[str, object]:
    """Everything on the Usage page, worked out from `ai_calls`."""
    year, number = int(month[:4]), int(month[5:7])
    days = calendar.monthrange(year, number)[1]
    zone = ZoneInfo(time_zone) if time_zone else UTC
    start, end = month_window(year, number, time_zone)
    rows = (session.scalars(select(AiCall).where(AiCall.at >= start, AiCall.at < end))).all()

    spent = sum((row.cost_usd for row in rows), Decimal(0))
    limit = get_setting(session, "spend_limit_usd")
    warn = get_setting(session, "spend_warn_percent")
    state = spending_state(month_spent(session, now), limit, warn)

    today = now.astimezone(zone)
    if (year, number) < (today.year, today.month):
        expected: Decimal = spent
    elif (year, number) == (today.year, today.month):
        expected = spent / today.day * days if today.day else spent
    else:
        expected = Decimal(0)

    def app_sums(app: str) -> Decimal:
        return sum((row.cost_usd for row in rows if row.app == app), Decimal(0))

    chat_rows = [row for row in rows if row.app == "chat"]
    learner_rows = [row for row in rows if row.app == "learner"]
    questions = {
        "count": len({row.message_id for row in chat_rows if row.message_id is not None}),
        "cost_usd": money(app_sums("chat")),
    }
    learning_runs = {
        "count": len(
            {row.learning_run_id for row in learner_rows if row.learning_run_id is not None}
        ),
        "cost_usd": money(app_sums("learner")),
    }

    def day_sums(app: str, day: int) -> Decimal:
        total = Decimal(0)
        for row in rows:
            if row.app != app:
                continue
            local = as_utc(row.at).astimezone(zone)
            if (local.year, local.month, local.day) == (year, number, day):
                total += row.cost_usd
        return total

    per_day = []
    for day in range(1, days + 1):
        per_day.append(
            {
                "date": f"{month}-{day:02d}",
                "questions_usd": money(day_sums("chat", day)),
                "learning_usd": money(day_sums("learner", day)),
                "tests_usd": money(day_sums("tests", day)),
            }
        )

    groups: dict[str, Decimal] = {}
    for row in rows:
        groups[group_for(row.job, row.app)] = (
            groups.get(group_for(row.job, row.app), Decimal(0)) + row.cost_usd
        )
    per_group = [
        {
            "group": group,
            "cost_usd": money(cost),
            "percent": round(float(cost) / float(spent) * 100, 1) if spent else 0.0,
        }
        for group, cost in sorted(groups.items(), key=lambda item: -item[1])
        if cost > 0
    ]

    # Private chats never surface here; their spend still counts above.
    assistant_rows = (
        session.scalars(
            select(Message)
            .join(Chat, Message.chat_id == Chat.id)
            .where(
                Message.role == "assistant",
                Chat.private.is_(False),
                Message.started_at >= start,
                Message.started_at < end,
                Message.cost_usd > 0,
            )
            .order_by(Message.cost_usd.desc())
            .limit(5)
        )
    ).all()
    top_questions = []
    for message in assistant_rows:
        before = session.scalar(
            select(Message)
            .where(
                Message.chat_id == message.chat_id,
                Message.role == "user",
                Message.id < message.id,
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        top_questions.append(
            {
                "message_id": message.id,
                "chat_id": message.chat_id,
                "question": before.text_ if before is not None else "",
                "asked_at": message.started_at.isoformat(),
                "seconds": message.seconds,
                "steps": message.steps,
                "cost_usd": money(message.cost_usd),
            }
        )

    return {
        "month": month,
        "days_in_month": days,
        "resets_on": end.astimezone(zone).strftime("%Y-%m-%d"),
        "spent_usd": money(spent),
        "limit_usd": float(limit),
        "warn_percent": float(warn),
        "percent_used": round(float(spent) / float(limit) * 100, 1) if limit else 0.0,
        "state": state,
        "expected_usd": money(expected),
        "questions": questions,
        "learning_runs": learning_runs,
        "per_day": per_day,
        "per_group": per_group,
        "top_questions": top_questions,
    }


@usage_router.get("/api/usage", response_model=UsageSummary)
def get_usage(
    session: Session = Depends(get_session),
    month: str | None = Query(default=None),
) -> dict[str, object]:
    now = datetime.now(UTC)
    time_zone = get_setting(session, "time_zone")
    return build_usage(session, parse_month(month, time_zone, now), time_zone, now)
