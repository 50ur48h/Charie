"""The setup guide state on the real API."""

from charie.shared.knowledge import versions
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.questions import OwnerQuestion
from charie.shared.tables.sources import DataSource
from tests.conftest import log_in


def _get(client):
    response = client.get("/api/setup")
    assert response.status_code == 200, response.text
    return response.json()


def _source(db_session) -> None:
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
        )
    )
    db_session.commit()


def test_fresh_database_is_step_1(learner_client) -> None:
    log_in(learner_client)
    assert _get(learner_client) == {
        "setup_done": False,
        "step": 1,
        "readiness": None,
        "usability": None,
    }


def test_connected_source_is_step_2(learner_client, db_session) -> None:
    log_in(learner_client)
    _source(db_session)
    assert _get(learner_client)["step"] == 2


def test_waiting_question_is_step_4(learner_client, db_session) -> None:
    log_in(learner_client)
    _source(db_session)
    db_session.add(LearningRun(kind="first", status="done"))
    db_session.add(
        OwnerQuestion(
            topic="Sales",
            title="What counts as a sale?",
            body="Pick one.",
            source="learning",
        )
    )
    db_session.commit()
    assert _get(learner_client)["step"] == 4


def test_readiness_is_null(learner_client) -> None:
    log_in(learner_client)
    assert _get(learner_client)["readiness"] is None


def test_readiness_served_from_draft(learner_client, db_session) -> None:
    log_in(learner_client)
    draft = versions.get_or_create_draft(db_session, "first_learning")
    report = {
        "numbers_checked": 2,
        "numbers_total": 2,
        "numbers_waiting": 0,
        "practice_right": 1,
        "practice_total": 1,
        "weak_area": None,
        "weak_area_why": "Charie did well everywhere.",
    }
    draft.readiness = report
    db_session.commit()
    assert _get(learner_client)["readiness"] == report
