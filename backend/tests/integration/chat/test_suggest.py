"""POST /api/knowledge/{key}/suggest queues a correction to-do (P12.2)."""

from charie.shared.tables.knowledge import KbEntry, KbVersion
from charie.shared.tables.questions import LearnerTodo
from tests.conftest import log_in


def _published(db_session, number: int = 2) -> KbVersion:
    version = KbVersion(number=number, status="published", made_by="first_learning")
    db_session.add(version)
    db_session.commit()
    db_session.add(
        KbEntry(
            version_id=version.id,
            key="metric.net_sales",
            kind="metric",
            title="Net sales",
            meaning="Money kept after refunds.",
            details={},
            confidence="checked",
            sources=[],
        )
    )
    db_session.commit()
    return version


def test_suggestion_goes_to_the_learner_todo_list(chat_client, db_session) -> None:
    """A suggestion becomes an open correction with the entry attached."""
    log_in(chat_client)
    version = _published(db_session)
    response = chat_client.post(
        "/api/knowledge/metric.net_sales/suggest", json={"text": "  Exclude staff meals  "}
    )
    assert response.status_code == 201, response.text
    todo_id = response.json()["todo_id"]
    todo = db_session.get(LearnerTodo, todo_id)
    assert todo is not None
    assert todo.kind == "correction"
    assert todo.status == "open"
    assert todo.text_ == "Exclude staff meals"
    assert todo.details == {
        "entry_key": "metric.net_sales",
        "entry_title": "Net sales",
        "kb_version": version.number,
        "words": 3,
    }


def test_suggest_unknown_key_is_not_found(chat_client, db_session) -> None:
    """An unknown key gets `not_found`, not a to-do."""
    log_in(chat_client)
    _published(db_session)
    response = chat_client.post("/api/knowledge/nope/suggest", json={"text": "Try this"})
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert "no knowledge entry called nope" in response.json()["message"]


def test_suggest_empty_text_is_refused(chat_client, db_session) -> None:
    """Blank text gets `empty_text`."""
    log_in(chat_client)
    _published(db_session)
    response = chat_client.post("/api/knowledge/metric.net_sales/suggest", json={"text": "   "})
    assert response.status_code == 400
    assert response.json() == {"error": "empty_text", "message": "Write your suggestion first."}
