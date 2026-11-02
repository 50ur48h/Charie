"""`GET /api/status` after P12.1: every field, the still-learning shape."""

from tests.conftest import log_in


def _get(chat_client):
    response = chat_client.get("/api/status")
    assert response.status_code == 200, response.text
    return response.json()


def test_status_has_every_field(chat_client) -> None:
    """The full shape both apps share (P12.1)."""
    log_in(chat_client)
    assert set(_get(chat_client).keys()) == {
        "knowledge",
        "data",
        "learning",
        "spending",
        "questions_waiting",
        "learner_url",
    }


def test_before_first_version_knowledge_is_null(chat_client) -> None:
    """No published version yet: null version and zero counts."""
    log_in(chat_client)
    status = _get(chat_client)
    assert status["knowledge"] == {
        "version": None,
        "entries": 0,
        "documents": 0,
        "published_at": None,
    }
    assert status["learning"] == {"status": "none", "step_title": None, "percent": 0}
    assert status["data"] is None


def test_learner_url_comes_from_the_setting(chat_client, monkeypatch) -> None:
    """`learner_url` follows `CHARIE_LEARNER_URL`, defaulting to the laptop."""
    from charie.shared.config import get_settings

    log_in(chat_client)
    assert _get(chat_client)["learner_url"] == "http://localhost:5174"
    monkeypatch.setenv("CHARIE_LEARNER_URL", "http://learner.example")
    get_settings.cache_clear()
    try:
        assert _get(chat_client)["learner_url"] == "http://learner.example"
    finally:
        get_settings.cache_clear()
