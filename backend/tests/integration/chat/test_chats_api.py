"""The chat addresses on the real API (P10.1)."""

import asyncio
import threading
import time
from datetime import UTC, datetime

from sqlalchemy import select

from charie.chat.analyst import runner as runner_module
from charie.shared.tables.chat import Message
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.sources import DataSource
from charie.shared.tables.usage import AiCall
from tests.conftest import log_in
from tests.integration.chat.conftest import fake_understanding


def _publish(db_session) -> KbVersion:
    version = KbVersion(number=1, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.commit()
    return version


def _stall_answer(monkeypatch):
    """Hold the analyst before it answers; the caller frees the event."""
    release = threading.Event()
    real_answer = runner_module.answer_question

    async def _stalled(ctx) -> None:
        await asyncio.to_thread(release.wait, 10)
        await real_answer(ctx)

    monkeypatch.setattr(runner_module, "answer_question", _stalled)
    return release


def _wait_done(client, chat_id) -> dict:
    for _ in range(100):
        opened = client.get(f"/api/chats/{chat_id}").json()
        if opened["messages"][1]["status"] == "done":
            return opened
        time.sleep(0.05)
    return client.get(f"/api/chats/{chat_id}").json()


def _ask(client, chat_id, text="Net sales in December 2025", mode="thinking"):
    response = client.post(f"/api/chats/{chat_id}/messages", json={"text": text, "mode": mode})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_chats(chat_client, db_session) -> None:
    log_in(chat_client)
    first = chat_client.post("/api/chats", json={}).json()
    second = chat_client.post("/api/chats", json={}).json()
    assert first["title"] == "New chat"
    listed = chat_client.get("/api/chats").json()["chats"]
    assert [row["id"] for row in listed] == [second["id"], first["id"]]


def test_rename_chat(chat_client, db_session) -> None:
    log_in(chat_client)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    renamed = chat_client.patch(f"/api/chats/{chat_id}", json={"title": "December review"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "December review"


def test_rename_rejects_bad_title(chat_client, db_session) -> None:
    log_in(chat_client)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    for bad in ("", "x" * 81):
        response = chat_client.patch(f"/api/chats/{chat_id}", json={"title": bad})
        assert response.status_code == 422, bad
        assert response.json()["error"] == "bad_title"


def test_open_chat_returns_messages_and_thinking(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    ids = _ask(chat_client, chat_id)
    opened = chat_client.get(f"/api/chats/{chat_id}").json()
    assert [message["id"] for message in opened["messages"]] == [
        ids["user_message_id"],
        ids["assistant_message_id"],
    ]
    assert opened["messages"][0]["role"] == "user"
    assert opened["messages"][0]["status"] == "done"
    _wait_done(chat_client, chat_id)


def test_missing_chat_is_404(chat_client, db_session) -> None:
    log_in(chat_client)
    response = chat_client.get("/api/chats/999999")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_delete_chat_keeps_ai_calls(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    ids = _ask(chat_client, chat_id)
    for _ in range(100):
        if chat_client.get(f"/api/chats/{chat_id}").json()["messages"][1]["status"] == "done":
            break
        time.sleep(0.05)
    db_session.add(
        AiCall(
            app="chat",
            job="understand_question",
            provider="meta",
            model="muse-wonder-1.0",
            message_id=ids["assistant_message_id"],
        )
    )
    db_session.commit()
    assert chat_client.delete(f"/api/chats/{chat_id}").status_code == 204
    kept = db_session.scalar(select(AiCall).order_by(AiCall.id.desc()).limit(1))
    assert kept is not None and kept.message_id is None


def test_delete_refused_while_running(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    release = _stall_answer(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    ids = _ask(chat_client, chat_id)
    try:
        db_session.expire_all()
        assert db_session.get(Message, ids["assistant_message_id"]).status == "thinking"
        response = chat_client.delete(f"/api/chats/{chat_id}")
        assert response.status_code == 409
        assert response.json()["error"] == "question_running"
    finally:
        release.set()
    assert _wait_done(chat_client, chat_id)["messages"][1]["status"] == "done"


def test_ask_creates_two_messages(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    _ask(chat_client, chat_id)
    for _ in range(100):
        opened = chat_client.get(f"/api/chats/{chat_id}").json()
        assistant = opened["messages"][1]
        if assistant["status"] == "done":
            break
        time.sleep(0.05)
    assert assistant["status"] == "done", assistant
    assert [line["title"] for line in assistant["thinking"]] == [
        "Understood the question",
        "Placeholder answer. Here's what I found:",
    ]
    assert (
        "Placeholder answer. Here's what I found:"
        in assistant["answer"]["blocks"][0]["sentences"][0]["text"]
    )


def test_ask_sets_title_from_first_question(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    question = "How did net sales by cuisine compare for the fourth quarter of 2025?"
    _ask(chat_client, chat_id, text=question)
    opened = chat_client.get(f"/api/chats/{chat_id}").json()
    assert opened["title"] == "How did net sales by cuisine compare for the fourth quarter…"
    _wait_done(chat_client, chat_id)


def test_ask_refused_while_running(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    release = _stall_answer(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    _ask(chat_client, chat_id)
    try:
        response = chat_client.post(f"/api/chats/{chat_id}/messages", json={"text": "And now?"})
        assert response.status_code == 409
        assert response.json()["error"] == "question_running"
    finally:
        release.set()
    assert _wait_done(chat_client, chat_id)["messages"][1]["status"] == "done"


def test_ask_refused_when_spending_paused(chat_client, db_session) -> None:
    log_in(chat_client)
    _publish(db_session)
    from charie.shared.settings import set_setting

    set_setting(db_session, "spend_limit_usd", 0)
    db_session.commit()
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    response = chat_client.post(f"/api/chats/{chat_id}/messages", json={"text": "Net sales?"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "spending_paused"
    assert body["message"] == (
        "New AI work is paused because this month's spending limit is reached. "
        "Raise the limit on the Usage page to continue."
    )


def test_ask_refused_without_published_version(chat_client, db_session) -> None:
    log_in(chat_client)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    response = chat_client.post(f"/api/chats/{chat_id}/messages", json={"text": "Net sales?"})
    assert response.status_code == 409
    assert response.json()["error"] == "not_ready"


def test_ask_rejects_empty_and_long_text(chat_client, db_session) -> None:
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    for text, code in (("   ", "empty_question"), ("x" * 2001, "question_too_long")):
        response = chat_client.post(f"/api/chats/{chat_id}/messages", json={"text": text})
        assert response.status_code == 422, text[:10]
        assert response.json()["error"] == code


def test_ask_rejects_quick_mode(chat_client, db_session) -> None:
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    response = chat_client.post(
        f"/api/chats/{chat_id}/messages", json={"text": "Net sales?", "mode": "quick"}
    )
    assert response.status_code == 422
    assert response.json()["error"] == "quick_not_ready"


def test_ask_saves_data_through_from_source(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    db_session.add(
        DataSource(
            kind="postgres",
            name="Charie Test database",
            host="localhost",
            port=5432,
            database="x",
            username="y",
            password_encrypted="zzz",
            status="connected",
            read_only_ok=True,
            data_through=datetime(2025, 12, 31, tzinfo=UTC),
        )
    )
    db_session.commit()
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    ids = _ask(chat_client, chat_id)
    saved = db_session.get(Message, ids["assistant_message_id"])
    assert saved.data_through is not None
    assert saved.data_through.isoformat().startswith("2025-12-31")
    _wait_done(chat_client, chat_id)


def test_chat_addresses_need_login(chat_client, db_session) -> None:
    assert chat_client.get("/api/chats").status_code == 401
    assert chat_client.post("/api/chats", json={}).status_code == 401
