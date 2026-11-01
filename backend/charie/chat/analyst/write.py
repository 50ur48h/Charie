"""The answer writer: labelled blocks from the checked notebook (P10.10)."""

from typing import Literal

from pydantic import BaseModel, Field

from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.labels import fill_labels
from charie.chat.analyst.notebook import Notebook
from charie.chat.analyst.understand import knowledge_summary
from charie.shared.ai.client import get_ai
from charie.shared.db import session_scope

JOB_KIND = "write_answer"


def _style_line(title: str, details) -> str:
    """One style rule as `title: text`, whatever shape the entry has."""
    if isinstance(details, dict):
        return f"{title}: {details.get('text', str(details))}"
    return f"{title}: {details}"


SentenceKind = Literal["fact", "conclusion", "possible_reason", "suggestion", "note"]
ChartKind = Literal["bar", "bar_diverging", "line", "bar_stacked"]
BlockType = Literal["text", "kpis", "chart", "table", "tree", "callout", "suggestions"]
TreeTone = Literal["good", "bad", "neutral"]
Confidence = Literal["likely", "worth_checking"]


class DraftSentence(BaseModel):
    """One answer sentence; code fills its labels and checks the copy."""

    kind: SentenceKind = Field(description="fact, conclusion, possible reason, suggestion or note.")
    text: str = Field(description="Labelled words, no bare numbers.")
    proof: list[str] = Field(default=[], description="The labels that prove it.")
    starts_paragraph: bool = Field(default=False, description="True starts a new paragraph.")


class DraftKpi(BaseModel):
    """One number card: a labelled value and its change."""

    title: str = Field(description="The card name; labels for periods, never years.")
    value: str = Field(default="", description="An n label, or empty.")
    change: str = Field(default="", description="An n label for the change, or empty.")
    spark: str = Field(default="", description="A t label for the spark line, or empty.")


class DraftChart(BaseModel):
    """One chart of a labelled table."""

    kind: ChartKind = Field(description="bar, bar_diverging, line or bar_stacked.")
    title: str = Field(description="The chart name; labels for periods, never years.")
    subtitle: str = Field(default="", description="The comparison, with labels.")
    table: str = Field(default="", description="The t label to draw.")
    x: str = Field(default="", description="The x column key.")
    y: str = Field(default="", description="The y column key.")
    highlight: list[str] = Field(default=[], description="The x values to mark.")


class DraftTable(BaseModel):
    """One table block: a labelled table and the columns to show."""

    title: str = Field(description="The table name; labels for periods, never years.")
    table: str = Field(default="", description="The t label to show.")
    columns: list[str] = Field(default=[], description="The column keys, in order.")


class DraftTreeNode(BaseModel):
    """One tree node; flat, with a parent id."""

    id: str = Field(description="This node's id.")
    parent: str = Field(default="", description="The parent id, or empty.")
    label: str = Field(description="Labelled words, no bare numbers.")
    tone: TreeTone = Field(default="neutral", description="good, bad or neutral.")


class DraftSuggestion(BaseModel):
    """One thing the owner might ask next."""

    text: str = Field(description="The suggestion in plain words.")
    confidence: Confidence = Field(
        default="worth_checking", description="likely or worth_checking."
    )


class DraftBlock(BaseModel):
    """One answer block; only the fields of its type are used."""

    type: BlockType = Field(description="text, kpis, chart, table, tree, callout or suggestions.")
    sentences: list[DraftSentence] = Field(default=[], description="The text sentences.")
    kpis: list[DraftKpi] = Field(default=[], description="The number cards.")
    chart: DraftChart | None = Field(default=None, description="The chart, if any.")
    table: DraftTable | None = Field(default=None, description="The table, if any.")
    tree_title: str = Field(default="", description="The tree name.")
    tree_nodes: list[DraftTreeNode] = Field(default=[], description="The flat nodes.")
    callout_tone: Literal["note", "warn"] = Field(default="note", description="note or warn.")
    callout_text: str = Field(default="", description="Labelled words, no bare numbers.")
    suggestions_title: str = Field(default="", description="The suggestions name.")
    suggestions: list[DraftSuggestion] = Field(default=[], description="The follow-ups.")


class AnswerDraft(BaseModel):
    """The writer's draft: blocks in the order they explain best."""

    blocks: list[DraftBlock] = Field(default=[], description="The answer blocks.")


def write_input(
    question: str,
    reading: str,
    kind: str,
    notebook: str,
    still_open: list[str],
    cannot_tell: list[str],
    stop_reason: str,
    problems: list,
    style_rules: list[str],
    answer_length: str,
    fixes: list[str],
) -> dict:
    """Every part of the writer's task, with the reading already filled."""
    return {
        "question": question,
        "reading": reading,
        "kind": kind,
        "notebook": notebook,
        "still_open": "; ".join(still_open) or "none",
        "cannot_tell": "; ".join(cannot_tell) or "none",
        "stop_reason": stop_reason or "answered",
        "problems": "; ".join(str(problem) for problem in problems) or "none",
        "style_rules": "\n".join(style_rules) or "none",
        "answer_length": answer_length,
        "fixes": "\n".join(fixes) or "none",
    }


def write_answer(ctx, fixes: list[str] | None = None) -> AnswerDraft:
    """Ask the writer once; the fix loop (P10.12) decides about retries."""
    with session_scope() as session:
        kb = KbView.load(session, ctx.kb_version_id)
        book = Notebook.load(session, ctx.message_id, ctx.chat_id)
        values: dict[str, str] = {}
        for item in book.items():
            filled = book.fill_value(item)
            if filled is not None:
                values[item.label] = filled
        reading = fill_labels(ctx.understanding.reading or "", values)
        styles = [_style_line(title, details) for title, details in sorted(kb.styles().items())]
        inputs = write_input(
            question=ctx.question,
            reading=reading,
            kind=ctx.understanding.kind,
            notebook=book.labelled_view(),
            still_open=list(ctx.still_open),
            cannot_tell=list(ctx.cannot_tell),
            stop_reason=ctx.stop_reason,
            problems=list(ctx.problems),
            style_rules=styles,
            answer_length=(ctx.settings or {}).get("answer_length", "normal"),
            fixes=list(fixes or []),
        )
        summary = knowledge_summary(kb)
    return get_ai().run(
        JOB_KIND,
        inputs,
        AnswerDraft,
        app="chat",
        message_id=ctx.message_id,
        knowledge_summary=summary,
        already_running=True,
    )
