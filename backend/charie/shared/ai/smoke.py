"""First real call: `name_chat` against Meta, saved in our database.

Run once: `uv run python -m charie.shared.ai.smoke`.
"""

import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import SpendingPaused
from charie.shared.db import session_scope
from charie.shared.tables.usage import AiCall


def latest_report(session: Session, job: str, app: str) -> dict[str, Any] | None:
    """The newest cost row for a job, copied while the session is open."""
    row = session.scalar(
        select(AiCall).where(AiCall.job == job, AiCall.app == app).order_by(AiCall.id.desc())
    )
    if row is None:
        return None
    return {
        "prompt_tokens": row.prompt_tokens,
        "cached_tokens": row.cached_tokens,
        "completion_tokens": row.completion_tokens,
        "reasoning_tokens": row.reasoning_tokens,
        "cost_usd": Decimal(str(row.cost_usd)),
    }


def main() -> int:
    try:
        result = get_ai().run("name_chat", {"topic": "test sales question"}, ChatTitle, app="tests")
    except SpendingPaused as err:
        print(err.message)
        return 1
    with session_scope() as session:
        report = latest_report(session, "name_chat", "tests")
    print(f"Title: {result.title}")
    if report is None:
        print("The call worked, but no cost row was saved.")
        return 1
    print(f"Prompt tokens: {report['prompt_tokens']} ({report['cached_tokens']} cached)")
    print(
        f"Completion tokens: {report['completion_tokens']} ({report['reasoning_tokens']} reasoning)"
    )
    print(f"Cost: ${report['cost_usd']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
