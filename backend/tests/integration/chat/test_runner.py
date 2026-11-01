"""The background runner on the real database (P10.1)."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from charie.chat.analyst import answer as answer_module
from charie.chat.analyst import runner as runner_module
from charie.chat.analyst.runner import RUNNING, request_finish, run_now
from charie.shared.tables.chat import Chat, Message, ThinkingEvent
from charie.shared.tables.knowledge import KbVersion


def _thinking_assistant(db_session, status="thinking") -> Message:
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.flush()
    user_message = Message(
        chat_id=chat.id,
        role="user",
        text_="Net sales?",
        status="done",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    assistant = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status=status,
        mode="thinking",
        kb_version_id=version.id,
        started_at=datetime.now(UTC),
    )
    db_session.add(user_message)
    db_session.add(assistant)
    db_session.commit()
    return assistant


def test_thinking_log_saves_and_updates(db, db_session) -> None:
    from charie.chat.analyst.stream import ThinkingLog

    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    message = Message(chat_id=chat.id, role="assistant", text_="", started_at=datetime.now(UTC))
    db_session.add(message)
    db_session.commit()
    log = ThinkingLog(message.id)
    first = log.start("step", "Reading your question")
    second = log.add("check", "Placeholder check")
    assert (first, second) == (1, 2)
    log.finish(first, status="done")
    lines = log.lines()
    assert [line["seq"] for line in lines] == [1, 2]
    assert all(line["status"] == "done" for line in lines)


def test_placeholder_answer_saved(db, db_session, monkeypatch) -> None:
    monkeypatch.setattr(answer_module, "PLACEHOLDER_PAUSE", 0)
    assistant = _thinking_assistant(db_session)
    asyncio.run(run_now(assistant.id))
    db_session.expire_all()
    saved = db_session.get(Message, assistant.id)
    assert saved.status == "done"
    assert saved.finished_at is not None
    assert "placeholder answer" in saved.answer["blocks"][0]["sentences"][0]["text"]
    titles = db_session.scalars(
        select(ThinkingEvent.title)
        .where(ThinkingEvent.message_id == assistant.id)
        .order_by(ThinkingEvent.seq)
    ).all()
    assert titles == [
        "Reading your question",
        "Placeholder: the real analyst is being built",
        "Placeholder check",
    ]


def test_finish_now_skips_remaining_lines(db, db_session, monkeypatch) -> None:
    monkeypatch.setattr(answer_module, "PLACEHOLDER_PAUSE", 0.3)
    assistant = _thinking_assistant(db_session)

    async def _run() -> None:
        task = asyncio.create_task(run_now(assistant.id))
        await asyncio.sleep(0.1)
        assert request_finish(assistant.id) is True
        await task

    asyncio.run(_run())
    saved = db_session.get(Message, assistant.id)
    assert saved.status == "thinking"
    assert saved.answer is None
    lines = db_session.scalars(
        select(ThinkingEvent).where(ThinkingEvent.message_id == assistant.id)
    ).all()
    assert len(lines) < 3


@pytest.mark.asyncio
async def test_start_runs_in_background(db, db_session, monkeypatch) -> None:
    monkeypatch.setattr(answer_module, "PLACEHOLDER_PAUSE", 0)
    assistant = _thinking_assistant(db_session)
    task = runner_module.start(assistant.id)
    await task
    assert RUNNING.get(assistant.id) is None
    db_session.expire_all()
    assert db_session.get(Message, assistant.id).status == "done"


def test_finish_after_end_is_409(chat_client, db_session, monkeypatch) -> None:
    from tests.conftest import log_in

    monkeypatch.setattr(answer_module, "PLACEHOLDER_PAUSE", 0)
    log_in(chat_client)
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.commit()
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    ids = chat_client.post(f"/api/chats/{chat_id}/messages", json={"text": "Net sales?"}).json()
    import time

    for _ in range(100):
        opened = chat_client.get(f"/api/chats/{chat_id}").json()
        if opened["messages"][1]["status"] == "done":
            break
        time.sleep(0.05)
    response = chat_client.post(f"/api/messages/{ids['assistant_message_id']}/finish")
    assert response.status_code == 409
    assert response.json()["error"] == "not_running"


def test_run_now_marks_failed_and_raises(db, db_session, monkeypatch) -> None:
    assistant = _thinking_assistant(db_session)

    async def _boom(_ctx) -> None:
        raise RuntimeError("nope")

    monkeypatch.setattr(runner_module, "answer_question", _boom)
    with pytest.raises(RuntimeError):
        asyncio.run(run_now(assistant.id))
    db_session.expire_all()
    saved = db_session.get(Message, assistant.id)
    assert saved.status == "failed"
    assert saved.finished_at is not None
    note = db_session.scalar(
        select(ThinkingEvent)
        .where(ThinkingEvent.message_id == assistant.id, ThinkingEvent.kind == "note")
        .limit(1)
    )
    assert note is not None and note.status == "failed"
    assert note.body == "Something went wrong while answering. Please ask again."


def test_startup_marks_running_messages_stopped(db, db_session) -> None:
    from fastapi.testclient import TestClient

    from charie.chat.app import STOPPED_BODY, build_app

    assistant = _thinking_assistant(db_session)
    with TestClient(build_app()):
        pass
    saved = db_session.get(Message, assistant.id)
    assert saved.status == "stopped"
    note = db_session.scalar(
        select(ThinkingEvent)
        .where(ThinkingEvent.message_id == assistant.id, ThinkingEvent.kind == "note")
        .limit(1)
    )
    assert note is not None and note.status == "failed" and note.body == STOPPED_BODY
