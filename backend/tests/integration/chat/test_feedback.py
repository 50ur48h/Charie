"""Votes and corrections on a saved answer (P12.3)."""

from datetime import UTC, datetime

from sqlalchemy import select

from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.questions import LearnerTodo
from tests.conftest import log_in


def _chat(db_session, question="How are we doing?", status="done"):
    """A chat with one user question and its assistant answer."""
    chat = Chat(title="New chat")
    db_session.add(chat)
    db_session.flush()
    db_session.add(
        Message(
            chat_id=chat.id,
            role="user",
            text_=question,
            status="done",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
    )
    db_session.flush()
    message = Message(
        chat_id=chat.id,
        role="assistant",
        text_="",
        status=status,
        mode="thinking",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db_session.add(message)
    db_session.commit()
    return chat.id, message.id


def test_voting_twice_keeps_one_vote(chat_client, db_session) -> None:
    """Up, up and clear: the last vote wins, null clears it."""
    log_in(chat_client)
    _, message_id = _chat(db_session)
    assert chat_client.post(f"/api/messages/{message_id}/feedback", json={"vote": "up"}).json() == {
        "vote": "up"
    }
    assert db_session.get(Message, message_id).feedback == "up"
    assert chat_client.post(f"/api/messages/{message_id}/feedback", json={"vote": "up"}).json() == {
        "vote": "up"
    }
    assert chat_client.post(f"/api/messages/{message_id}/feedback", json={"vote": None}).json() == {
        "vote": None
    }
    assert db_session.get(Message, message_id).feedback is None


def test_feedback_rejects_a_bad_vote(chat_client, db_session) -> None:
    """Anything but up, down or null gets `bad_vote`."""
    log_in(chat_client)
    _, message_id = _chat(db_session)
    response = chat_client.post(f"/api/messages/{message_id}/feedback", json={"vote": "maybe"})
    assert response.status_code == 400
    assert response.json() == {"error": "bad_vote", "message": "Vote up, down or clear it."}


def test_feedback_saves_a_note_and_clears_it(chat_client, db_session) -> None:
    """A note is saved with the vote; clearing the vote clears the note."""
    log_in(chat_client)
    _, message_id = _chat(db_session)
    response = chat_client.post(
        f"/api/messages/{message_id}/feedback", json={"vote": "down", "note": "Wrong month."}
    )
    assert response.status_code == 200
    assert db_session.get(Message, message_id).feedback_note == "Wrong month."
    response = chat_client.post(f"/api/messages/{message_id}/feedback", json={"vote": None})
    assert response.json() == {"vote": None}
    assert db_session.get(Message, message_id).feedback_note is None


def test_feedback_rejects_a_long_note(chat_client, db_session) -> None:
    """A note over 500 characters gets `note_too_long`."""
    log_in(chat_client)
    _, message_id = _chat(db_session)
    response = chat_client.post(
        f"/api/messages/{message_id}/feedback", json={"vote": "up", "note": "x" * 501}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "note_too_long"


def test_feedback_unknown_message_is_not_found(chat_client) -> None:
    """Voting on nothing gets `not_found`."""
    log_in(chat_client)
    response = chat_client.post("/api/messages/999999/feedback", json={"vote": "up"})
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_rating_an_unfinished_message_is_refused(chat_client, db_session) -> None:
    """A running answer and a user message get `not_an_answer` on both addresses."""
    log_in(chat_client)
    chat_id, message_id = _chat(db_session, status="thinking")
    user_id = db_session.scalar(
        select(Message.id).where(Message.chat_id == chat_id, Message.role == "user").limit(1)
    )
    for address, body in [
        (f"/api/messages/{message_id}/feedback", {"vote": "up"}),
        (f"/api/messages/{message_id}/wrong", {"correction": "Nope"}),
        (f"/api/messages/{user_id}/feedback", {"vote": "up"}),
        (f"/api/messages/{user_id}/wrong", {"correction": "Nope"}),
    ]:
        response = chat_client.post(address, json=body)
        assert response.status_code == 409, (address, response.text)
        assert response.json() == {
            "error": "not_an_answer",
            "message": "You can only rate a finished answer.",
        }


def test_sending_a_correction_queues_a_todo(chat_client, db_session) -> None:
    """A correction becomes an open correction to-do with the question attached."""
    log_in(chat_client)
    chat_id, message_id = _chat(db_session, question="How are we doing?")
    response = chat_client.post(
        f"/api/messages/{message_id}/wrong", json={"correction": "  Exclude staff meals  "}
    )
    assert response.status_code == 201, response.text
    todo = db_session.get(LearnerTodo, response.json()["todo_id"])
    assert todo is not None
    assert todo.kind == "correction"
    assert todo.status == "open"
    assert todo.text_ == "Exclude staff meals"
    assert todo.details == {
        "chat_id": chat_id,
        "message_id": message_id,
        "question": "How are we doing?",
        "words": "Exclude staff meals",
    }
    # The vote is untouched.
    assert db_session.get(Message, message_id).feedback is None


def test_wrong_rejects_a_long_correction(chat_client, db_session) -> None:
    """A correction over 2,000 characters gets `correction_too_long`."""
    log_in(chat_client)
    _, message_id = _chat(db_session)
    response = chat_client.post(
        f"/api/messages/{message_id}/wrong", json={"correction": "x" * 2001}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "correction_too_long"


def test_wrong_empty_text_and_unknown_message(chat_client, db_session) -> None:
    """Blank text gets `empty_text`; an unknown message gets `not_found`."""
    log_in(chat_client)
    _, message_id = _chat(db_session)
    response = chat_client.post(f"/api/messages/{message_id}/wrong", json={"correction": "   "})
    assert response.status_code == 400
    assert response.json() == {"error": "empty_text", "message": "Please write what's wrong."}
    response = chat_client.post("/api/messages/999999/wrong", json={"correction": "Nope"})
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_the_chat_shows_each_messages_feedback(chat_client, db_session) -> None:
    """GET the chat returns the saved vote on its message."""
    log_in(chat_client)
    chat_id, message_id = _chat(db_session)
    chat_client.post(f"/api/messages/{message_id}/feedback", json={"vote": "up"})
    response = chat_client.get(f"/api/chats/{chat_id}")
    assert response.status_code == 200, response.text
    votes = {
        item["id"]: item.get("feedback")
        for item in response.json()["messages"]
        if item["role"] == "assistant"
    }
    assert votes[message_id] == "up"
