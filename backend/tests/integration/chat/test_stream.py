"""The live stream on the real API (P10.2)."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from charie.chat.analyst.stream import FEEDS, MessageFeed
from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.knowledge import KbVersion
from tests.conftest import log_in
from tests.integration.chat.conftest import fake_understanding


def _publish(db_session) -> None:
    db_session.add(KbVersion(number=1, status="published", made_by="first_learning"))
    db_session.commit()


def _parse_sse(text: str) -> list[dict]:
    """Blank-line separated events into {id, event, data} dicts."""
    events = []
    for chunk in text.replace("\r\n", "\n").split("\n\n"):
        item: dict = {}
        for line in chunk.splitlines():
            if line.startswith("id:"):
                item["id"] = line[3:].strip()
            elif line.startswith("event:"):
                item["event"] = line[6:].strip()
            elif line.startswith("data:"):
                item["data"] = json.loads(line[5:].strip())
        if item:
            events.append(item)
    return events


def _wait_done(client, chat_id: int, timeout_s: float = 10.0) -> dict:
    """Poll the chat until the assistant message finishes."""
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        opened = client.get(f"/api/chats/{chat_id}").json()
        assistant = opened["messages"][1]
        if assistant["status"] == "done":
            return assistant
        time.sleep(0.05)
    raise AssertionError("the placeholder answer never finished")


def test_feed_ids_count_up_from_one() -> None:
    feed = MessageFeed()
    assert [feed.add("thinking", {"seq": 1}).id, feed.add("done", {}).id] == [1, 2]


@pytest.mark.asyncio
async def test_feed_follow_waits_for_new_events() -> None:
    feed = MessageFeed()
    seen: list = []

    async def _collect() -> None:
        async for item in feed.follow(0):
            seen.append((item.id, item.event))

    task = asyncio.create_task(_collect())
    await asyncio.sleep(0.05)
    feed.add("thinking", {"seq": 1})
    feed.add("done", {})
    feed.close()
    await asyncio.wait_for(task, timeout=5)
    assert seen == [(1, "thinking"), (2, "done")]


@pytest.mark.asyncio
async def test_feed_follow_drains_events_added_before_close() -> None:
    """Events that land after the replay snapshot still reach a follower."""
    feed = MessageFeed()
    feed.add("thinking", {"seq": 1})
    seen: list = []
    gen = feed.follow(0)
    try:
        seen.append(await gen.__anext__())
        feed.add("thinking", {"seq": 2})
        feed.add("done", {})
        feed.close()
        async for item in gen:
            seen.append(item)
    finally:
        await gen.aclose()
    assert [(item.id, item.event) for item in seen] == [
        (1, "thinking"),
        (2, "thinking"),
        (3, "done"),
    ]


def test_stream_sends_thinking_summary_blocks_done(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    assistant_id = chat_client.post(
        f"/api/chats/{chat_id}/messages", json={"text": "Net sales?"}
    ).json()["assistant_message_id"]
    events = _parse_sse(chat_client.get(f"/api/messages/{assistant_id}/stream").text)
    assert [event["event"] for event in events] == [
        "thinking",
        "thinking",
        "thinking",
        "thinking",
        "thinking",
        "thinking",
        "thinking",
        "thinking",
        "summary",
        "block",
        "text",
        "done",
    ]
    assert [event["id"] for event in events] == [str(n) for n in range(1, 13)]
    assert events[-1]["data"]["status"] == "done"


def test_stream_reconnect_sends_only_missed_events(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    assistant_id = chat_client.post(
        f"/api/chats/{chat_id}/messages", json={"text": "Net sales?"}
    ).json()["assistant_message_id"]
    first: list[dict] = []
    with chat_client.stream("GET", f"/api/messages/{assistant_id}/stream") as response:
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            first = _parse_sse(buffer)
            if len(first) >= 2:
                break
    assert [event["id"] for event in first] == ["1", "2"]
    rest = _parse_sse(
        chat_client.get(f"/api/messages/{assistant_id}/stream", headers={"Last-Event-ID": "2"}).text
    )
    assert [event["id"] for event in rest] == [str(n) for n in range(3, 13)]
    assert rest[-1] == {
        "id": "12",
        "event": "done",
        "data": {"message_id": assistant_id, "status": "done", "cost_usd": 0},
    }


def test_stream_after_end_rebuilds_from_database(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    assistant_id = chat_client.post(
        f"/api/chats/{chat_id}/messages", json={"text": "Net sales?"}
    ).json()["assistant_message_id"]
    _wait_done(chat_client, chat_id)
    FEEDS.pop(assistant_id, None)
    events = _parse_sse(chat_client.get(f"/api/messages/{assistant_id}/stream").text)
    assert [event["event"] for event in events] == [
        "reset",
        "thinking",
        "thinking",
        "thinking",
        "thinking",
        "thinking",
        "summary",
        "done",
    ]
    assert events[0]["id"] == "0"
    assert events[-1]["data"]["status"] == "done"


def test_stream_for_stopped_message_sends_done_stopped(db, db_session, monkeypatch) -> None:
    from charie.chat.app import build_app

    monkeypatch.setenv("CHARIE_PASSWORD", "test-password")
    monkeypatch.setenv("CHARIE_SECRET_KEY", "test-secret-key-for-tests-only")

    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    message = Message(chat_id=chat.id, role="assistant", text_="", status="thinking")
    db_session.add(message)
    db_session.commit()
    message_id = message.id
    with TestClient(
        build_app(), base_url="http://testserver", headers={"Origin": "http://testserver"}
    ) as client:
        log_in(client)
        events = _parse_sse(client.get(f"/api/messages/{message_id}/stream").text)
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["status"] == "stopped"


def test_stream_unknown_message_is_404(chat_client, db_session) -> None:
    log_in(chat_client)
    response = chat_client.get("/api/messages/999999/stream")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_stream_user_message_is_404(chat_client, db_session, monkeypatch) -> None:
    fake_understanding(monkeypatch)
    log_in(chat_client)
    _publish(db_session)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    ids = chat_client.post(f"/api/chats/{chat_id}/messages", json={"text": "Net sales?"}).json()
    response = chat_client.get(f"/api/messages/{ids['user_message_id']}/stream")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    _wait_done(chat_client, chat_id)
