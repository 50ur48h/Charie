"""First real call: `name_chat` against Meta, saved in our database.

Run once: `uv run python -m charie.shared.ai.smoke`.
"""

import sys

from sqlalchemy import select

from charie.chat.titles import ChatTitle
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import SpendingPaused
from charie.shared.db import session_scope
from charie.shared.tables.usage import AiCall


def main() -> int:
    try:
        result = get_ai().run("name_chat", {"topic": "test sales question"}, ChatTitle, app="tests")
    except SpendingPaused as err:
        print(err.message)
        return 1
    with session_scope() as session:
        row = session.scalar(
            select(AiCall)
            .where(AiCall.job == "name_chat", AiCall.app == "tests")
            .order_by(AiCall.id.desc())
        )
    print(f"Title: {result.title}")
    if row is None:
        print("The call worked, but no cost row was saved.")
        return 1
    print(f"Prompt tokens: {row.prompt_tokens} ({row.cached_tokens} cached)")
    print(f"Completion tokens: {row.completion_tokens} ({row.reasoning_tokens} reasoning)")
    print(f"Cost: ${row.cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
