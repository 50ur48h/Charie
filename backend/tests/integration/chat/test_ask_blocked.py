"""Asking before the first published version gets `still_learning` (P12.1)."""

from tests.conftest import log_in


def test_asking_before_first_version_gets_still_learning(chat_client) -> None:
    """No published knowledge yet: asking is refused with `still_learning`."""
    log_in(chat_client)
    chat = chat_client.post("/api/chats", json={}).json()
    response = chat_client.post(
        f"/api/chats/{chat['id']}/messages",
        json={"text": "How are we doing this month?", "mode": "thinking"},
    )
    assert response.status_code == 409, response.text
    assert response.json() == {
        "error": "still_learning",
        "message": (
            "Charie is still learning. You can ask questions once the first version "
            "of its knowledge is published."
        ),
    }
