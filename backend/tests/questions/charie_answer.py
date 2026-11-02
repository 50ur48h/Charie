"""Charie's real answer function (built in P10.14)."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, update

from charie.chat.analyst.context import RunState
from charie.chat.analyst.runner import run_now
from charie.chat.chat_store import (
    ask_question,
    chat_lock,
    create_chat,
)
from charie.shared.db import session_scope
from charie.shared.errors import ApiError
from charie.shared.tables.chat import Message, NotebookItem
from charie.shared.tables.usage import AiCall
from tests.questions.answers import ShownNumber, TestAnswer
from tests.questions.format import Question


class NotReadyError(Exception):
    """Charie is still learning; the harness stops before spending anything."""


def _answer_text(answer: dict | None) -> str:
    """The whole saved answer as plain text, reading first."""
    if not answer:
        return ""
    parts: list[str] = []
    for block in answer.get("blocks", []):
        kind = block.get("type")
        if kind == "reading":
            parts.append(block.get("text", ""))
        elif kind == "text":
            parts.append(
                "\n\n".join(
                    " ".join(
                        sentence.get("text", "") for sentence in paragraph.get("sentences", [])
                    )
                    for paragraph in block.get("paragraphs", [])
                )
            )
        elif kind == "table":
            lines = [block.get("title", "")]
            for row in block.get("rows", []):
                if isinstance(row, dict) and "what" in row:
                    value = row.get("value", {})
                    shown_value = (
                        value.get("f", value.get("v", "")) if isinstance(value, dict) else value
                    )
                    lines.append(f"{row.get('what', '')}: {shown_value}")
                else:
                    lines.append(str(row))
            parts.append("\n".join(line for line in lines if line))
        elif kind in ("callout", "method", "note"):
            parts.append(block.get("text", ""))
        elif kind == "follow_ups":
            parts.append("\n".join(block.get("items", [])))
    return "\n\n".join(part for part in parts if part)


def _shown_numbers(session, message_id: int, text: str) -> list[ShownNumber]:
    """The ok notebook numbers the saved answer shows (per its shown marks)."""
    _ = text
    shown: list[ShownNumber] = []
    items = session.scalars(select(NotebookItem).where(NotebookItem.message_id == message_id)).all()
    for item in items:
        if item.kind != "number" or item.status != "ok":
            continue
        if not (item.proof or {}).get("shown", False):
            continue
        value = item.value or {}
        shown.append(
            ShownNumber(
                label=item.label,
                value=Decimal(str(value.get("value", "0"))),
                unit=value.get("unit", ""),
                description=item.description,
            )
        )
    return shown


def _attribute_costs(session, chat_id: int) -> None:
    """The run's calls count as tests, so the report and usage agree."""
    message_ids = session.scalars(select(Message.id).where(Message.chat_id == chat_id)).all()
    if message_ids:
        session.execute(
            update(AiCall).where(AiCall.message_id.in_(message_ids)).values(app="tests")
        )
        session.commit()


def _turn_costs(session, chat_id: int, final_id: int) -> tuple[Decimal, Decimal]:
    """(Final-turn cost, earlier-turns cost) from the attributed calls."""
    rows = session.scalars(
        select(AiCall)
        .join(Message, AiCall.message_id == Message.id)
        .where(Message.chat_id == chat_id, AiCall.app == "tests")
    ).all()
    total = sum((Decimal(str(row.cost_usd)) for row in rows), Decimal("0"))
    final = sum(
        (Decimal(str(row.cost_usd)) for row in rows if row.message_id == final_id),
        Decimal("0"),
    )
    return final, total - final


async def _ask_turn(chat_id: int, text: str, private: bool, choice: str | None = None) -> int:
    """Ask one line and run it to a terminal status; returns the message id."""
    try:
        async with chat_lock(chat_id):
            with session_scope() as session:
                _, assistant = ask_question(session, chat_id, text, "thinking", choice)
                message_id = assistant.id
    except ApiError as err:
        if err.code == "still_learning":
            raise NotReadyError(err.message) from err
        raise
    await run_now(message_id, RunState(remember=False, name_chat=False), private=private)
    return message_id


def _read_turn(session, message_id: int) -> Message:
    message = session.get(Message, message_id)
    assert message is not None
    session.refresh(message)
    return message


def _summarize(
    session, chat_id: int, message_id: int, started: datetime, private: bool
) -> TestAnswer:
    """One finished turn as the scorer reads it: text, shown numbers, costs."""
    message = _read_turn(session, message_id)
    _attribute_costs(session, chat_id)
    final_cost, earlier_cost = _turn_costs(session, chat_id, message_id)
    text = _answer_text(message.answer)
    numbers = _shown_numbers(session, message_id, text)
    asked_choice = message.status == "needs_choice"
    if message.status == "failed":
        return TestAnswer(
            status="error",
            error="The analyst could not answer.",
            numbers=[],
            asked_choice=asked_choice,
            cost_usd=final_cost,
            earlier_turns_cost_usd=earlier_cost,
            seconds=(datetime.now(UTC) - started).total_seconds(),
            chat_url="" if private else f"/chat/{chat_id}",
        )
    return TestAnswer(
        status="ok",
        numbers=numbers,
        asked_choice=asked_choice,
        cost_usd=final_cost,
        earlier_turns_cost_usd=earlier_cost,
        seconds=(datetime.now(UTC) - started).total_seconds(),
        chat_url="" if private else f"/chat/{chat_id}",
        text=text,
    )


def _drop_chat(chat_id: int) -> None:
    """Remove a failed private chat, whatever its messages still read.

    The store refuses to delete a running question, but a crashed turn may
    still read "thinking": remove the row directly so failed hidden runs
    never leak into the chat list.
    """
    from charie.shared.tables.chat import Chat

    with session_scope() as session:
        try:
            chat = session.get(Chat, chat_id)
            if chat is not None:
                session.delete(chat)
            session.commit()
        except Exception:
            session.rollback()


def charie_answer(question: Question, private: bool) -> TestAnswer:
    """Run Charie in this same process (so it follows `AI_REPLAY`).

    Ask the `chat` lines, then the question, in one new chat; on an earlier
    turn, a quick question gets the first option. `text` is the whole final
    answer as plain text, "I read this as..." included. `numbers` are the `ok`
    notebook numbers whose labels the answer shows. `asked_choice` is true
    when the final message is `needs_choice`. `private=True` (hidden set)
    saves no memories or learner to-dos, and no chat link is reported.
    """
    started = datetime.now(UTC)
    chat_id: int | None = None
    try:
        with session_scope() as session:
            chat = create_chat(session, private=private)
            session.commit()
            chat_id = chat.id

        async def _run() -> int:
            final_id = 0
            turns = [*question.chat, question.question]
            for pos, text in enumerate(turns):
                final_id = await _ask_turn(chat_id, text, private)
                with session_scope() as session:
                    message = _read_turn(session, final_id)
                    if message.status == "needs_choice" and pos < len(turns) - 1:
                        options = (message.answer or {}).get("choice", {}).get("options", [])
                        if not options:
                            raise ValueError("The analyst needs a choice to continue.")
                        picked = options[0].get("id", "")
                        final_id = await _ask_turn(chat_id, text, private, picked)
            return final_id

        final_id = asyncio.run(_run())
        with session_scope() as session:
            return _summarize(session, chat_id, final_id, started, private)
    except NotReadyError:
        raise
    except Exception as error:
        final_cost, earlier_cost = Decimal("0"), Decimal("0")
        with session_scope() as session:
            if chat_id is not None:
                _attribute_costs(session, chat_id)
                # The crashed turn is the newest assistant message: no
                # later turn ran, so its spend is the final turn's.
                failed_id = session.scalar(
                    select(func.max(Message.id)).where(
                        Message.chat_id == chat_id, Message.role == "assistant"
                    )
                )
                if failed_id is not None:
                    final_cost, earlier_cost = _turn_costs(session, chat_id, failed_id)
        if private and chat_id is not None:
            _drop_chat(chat_id)
        return TestAnswer(
            status="error",
            text="",
            error=str(error),
            numbers=[],
            asked_choice=False,
            cost_usd=final_cost,
            earlier_turns_cost_usd=earlier_cost,
            seconds=(datetime.now(UTC) - started).total_seconds(),
            chat_url="",
        )
