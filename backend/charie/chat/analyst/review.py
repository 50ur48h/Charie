"""The reviewer's second pair of eyes (P10.12)."""

from typing import Literal

from pydantic import BaseModel, Field

from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.labels import fill_labels
from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.render import ai_filled_texts, values_for
from charie.chat.analyst.write import style_line
from charie.shared.ai.client import get_ai
from charie.shared.db import session_scope

JOB_KIND = "review_answer"


class ReviewFix(BaseModel):
    """One thing to fix, with the concrete change."""

    problem: str = Field(description="What is wrong, in plain words.")
    how_to_fix: str = Field(description="The concrete change, naming labels where it helps.")


class Review(BaseModel):
    """The reviewer's verdict: good, or what to fix."""

    verdict: Literal["good", "fix"] = Field(description="good, or fix.")
    fixes: list[ReviewFix] = Field(default=[], description="What to fix.")
    needs_more_data: bool = Field(default=False, description="True when a round could help.")
    missing_data: str = Field(default="", description="The missing data, as the focus.")


def review_answer(ctx, blocks: list[dict]) -> Review:
    """Ask the reviewer once; the fix loop decides about retries."""
    with session_scope() as session:
        kb = KbView.load(session, ctx.kb_version_id)
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        styles = [style_line(title, details) for title, details in sorted(kb.styles().items())]
        style = (ctx.settings or {}).get("number_format", "short")
        reading = fill_labels(ctx.understanding.reading or "", values_for(book.items(), style))
        inputs = {
            "question": ctx.question,
            "reading": reading,
            "notebook": book.short_view(),
            "style_rules": "\n".join(styles) or "none",
            "stop_reason": ctx.stop_reason or "answered",
            "answer": "\n".join(text for text in ai_filled_texts(blocks) if text) or "(empty)",
        }
        from charie.chat.analyst.understand import knowledge_summary

        summary = knowledge_summary(kb)
    return get_ai().run(
        JOB_KIND,
        inputs,
        Review,
        app="chat",
        message_id=ctx.message_id,
        knowledge_summary=summary,
        already_running=True,
    )
