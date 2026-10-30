"""GET /api/status on the real database (both apps share it)."""

from decimal import Decimal

from charie.shared.tables.questions import OwnerQuestion
from charie.shared.tables.sources import DataSource
from charie.shared.tables.usage import AiCall
from tests.conftest import log_in


def _get(client):
    response = client.get("/api/status")
    assert response.status_code == 200, response.text
    return response.json()


def _call(db_session, cost: str) -> None:
    db_session.add(
        AiCall(
            app="chat",
            job="write_answer",
            provider="meta",
            model="muse-wonder-1.0",
            cost_usd=Decimal(cost),
        )
    )
    db_session.commit()


def test_empty_database_status(chat_client) -> None:
    log_in(chat_client)
    assert _get(chat_client) == {
        "knowledge": {
            "version": None,
            "entries": 0,
            "documents": 0,
            "published_at": None,
        },
        "data": None,
        "learning": None,
        "spending": {
            "limit_usd": 150.0,
            "spent_usd": 0.0,
            "remaining_usd": 150.0,
            "percent_used": 0.0,
            "state": "ok",
        },
        "questions_waiting": 0,
    }


def test_saved_source_in_data(chat_client, db_session) -> None:
    log_in(chat_client)
    db_session.add(
        DataSource(
            kind="postgres",
            name="Bella Forno database",
            host="h",
            port=5432,
            database="d",
            username="u",
            password_encrypted="zzz",
            status="connected",
            read_only_ok=True,
        )
    )
    db_session.commit()
    data = _get(chat_client)["data"]
    assert data == {
        "name": "Bella Forno database",
        "kind": "postgres",
        "status": "connected",
        "data_through": None,
    }


def test_spending_states(chat_client, db_session) -> None:
    log_in(chat_client)
    _call(db_session, "10")
    assert _get(chat_client)["spending"]["state"] == "ok"
    _call(db_session, "110")
    assert _get(chat_client)["spending"]["state"] == "warn"
    _call(db_session, "30")
    spending = _get(chat_client)["spending"]
    assert spending["state"] == "paused"
    assert spending["spent_usd"] == 150.0


def test_both_apps_same_shape(chat_client, learner_client) -> None:
    log_in(chat_client)
    log_in(learner_client)
    assert chat_client.get("/api/status").json() == learner_client.get("/api/status").json()


def test_waiting_questions_counted(chat_client, db_session) -> None:
    log_in(chat_client)
    db_session.add(
        OwnerQuestion(topic="Sales", title="What counts?", body="Pick one.", source="learning")
    )
    db_session.commit()
    assert _get(chat_client)["questions_waiting"] == 1
