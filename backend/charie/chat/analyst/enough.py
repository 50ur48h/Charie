"""The enough check: do the rounds so far answer the question (P10.9)."""

from pydantic import BaseModel, Field

from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.understand import knowledge_summary
from charie.shared.ai.client import get_ai
from charie.shared.ai.errors import AiError
from charie.shared.db import session_scope

JOB_KIND = "check_enough"


class EnoughCheck(BaseModel):
    """Whether the labels so far answer the question."""

    enough: bool = Field(description="True when every part has a matching label.")
    missing: str = Field(default="", description="What is still unanswered, or empty.")


def run_check_enough(ctx, round_no: int) -> str:
    """Ask the AI once; add the check line; the missing text, or empty."""
    with session_scope() as session:
        kb = KbView.load(session, ctx.kb_version_id)
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        answers = "\n".join(f"[{item.label}] {item.description}" for item in book.items())
        summary = knowledge_summary(kb)
    try:
        form = get_ai().run(
            JOB_KIND,
            {
                "question": ctx.question,
                "round": round_no,
                "answers": answers or "none yet",
            },
            EnoughCheck,
            app="chat",
            message_id=ctx.message_id,
            knowledge_summary=summary,
            already_running=True,
        )
    except AiError:  # A broken check answers from the rounds finished.
        ctx.log.add(
            "check",
            "Checking whether the rounds so far answer the question.",
            "The check itself failed, so the rounds stop here.",
        )
        return ""
    if form.enough:
        ctx.log.add(
            "check",
            "Checking whether the rounds so far answer the question.",
            "Nothing missing.",
        )
        return ""
    body = form.missing.strip() or "more work"
    ctx.log.add(
        "check",
        "Checking whether the rounds so far answer the question.",
        body,
    )
    return body
