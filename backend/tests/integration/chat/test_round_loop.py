"""A fresh round loop on the practice database (P10.9 Task 4).

Laptop-only: needs the practice database and the recorded AI replies.
Recording is a fresh run (about $1–3): run
`AI_REPLAY=record uv run pytest <this file>` once with the owner's yes,
try the screen yourself, then replay. Without cassettes it fails by
design, like the new-kind questions.
"""

import time
from pathlib import Path

import pytest
from sqlalchemy import select

from charie.chat.analyst.notebook import Notebook
from charie.shared.tables.chat import Message, ThinkingEvent
from tests.conftest import log_in
from tests.integration.chat.test_answer_key_practice import _seed_net_sales
from tests.questions.format import load_questions

PUBLIC = Path(__file__).resolve().parents[2] / "questions" / "public.yaml"


@pytest.mark.practice_db
@pytest.mark.live_ai
def test_round_loop_fresh_run(chat_client, db_session, monkeypatch) -> None:
    """A new question runs rounds, fills the notebook and leaves lines."""
    question = next(
        item for item in load_questions(str(PUBLIC), "public") if item.id == "vague-001"
    )
    _seed_net_sales(db_session)
    log_in(chat_client)
    chat_id = chat_client.post("/api/chats", json={}).json()["id"]
    assistant_id = chat_client.post(
        f"/api/chats/{chat_id}/messages", json={"text": question.question}
    ).json()["assistant_message_id"]
    assistant = {}
    for _ in range(300):
        opened = chat_client.get(f"/api/chats/{chat_id}").json()
        assistant = next(item for item in opened["messages"] if item["id"] == assistant_id)
        if assistant["status"] == "done":
            break
        time.sleep(1.0)
    assert assistant["status"] == "done", assistant
    lines = db_session.scalars(
        select(ThinkingEvent).where(ThinkingEvent.message_id == assistant_id)
    ).all()
    rounds = [
        line
        for line in lines
        if line.kind == "step" and line.title.startswith("Round") and line.status == "done"
    ]
    assert rounds, "no round ran"
    checks = [line for line in lines if line.kind == "check" and line.status == "done"]
    assert checks, "the enough check never ran"
    book = Notebook.load(db_session, assistant_id, chat_id)
    assert book.items(), "the notebook is empty"
    assert [line for line in lines if line.status == "failed"] == []
    assert db_session.get(Message, assistant_id).status == "done"
