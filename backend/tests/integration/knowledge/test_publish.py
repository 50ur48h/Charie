"""Publishing versions: atomic setup finish, one live version (P09.9)."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from charie.shared.db import session_scope
from charie.shared.knowledge import store, versions
from charie.shared.tables.chat import Chat, Message
from charie.shared.tables.knowledge import KbVersion
from charie.shared.tables.learning import LearningRun
from tests.conftest import log_in


@pytest.fixture()
def version_id(db_session):
    return versions.get_or_create_draft(db_session, "first_learning").id


def _seed_small(db_session, version_id: int) -> None:
    """A small-only change: a fresh name entry."""
    store.upsert_entry(
        db_session,
        version_id,
        "name.shop.restaurants.name",
        "name",
        "Restaurant names",
        "Restaurant names",
        {"table": "shop.restaurants", "id_column": "id", "name_column": "name", "items": []},
        "guessed",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )
    db_session.commit()


def _seed_big(db_session, version_id: int) -> None:
    """A big change: a new recipe."""
    store.upsert_entry(
        db_session,
        version_id,
        "metric.net_sales",
        "metric",
        "Net sales",
        "Net sales",
        {
            "kind": "simple",
            "title": "Net sales",
            "table": "shop.orders",
            "aggregate": "sum",
            "expression": "orders.total_amount",
            "filters": [],
            "time_column": "orders.created_at",
            "time_column_type": "timestamptz",
            "unit": "money",
            "currency": "USD",
            "steps_in_words": ["Add them up.", "Keep the kept rows."],
            "dimensions": [],
            "tests": [],
            "reported_checks": [],
            "sql_preview": "seed",
            "tested_at": "2000-01-01T00:00:00+00:00",
        },
        "guessed",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )
    db_session.commit()


def _seed_big_passing(db_session, version_id: int) -> None:
    """A big change whose checks all pass: reviewable, publishable by the owner."""
    _seed_big(db_session, version_id)
    entry = store.get_entry(db_session, version_id, "metric.net_sales")
    details = dict(entry.details)
    details["tests"] = [
        {"name": "runs", "passed": True, "text": "seed"},
        {"name": "believable", "passed": True, "text": "seed"},
        {"name": "matches_documents", "passed": True, "text": "seed"},
        {"name": "parts_add_up", "passed": True, "text": "seed"},
    ]
    details["tested_at"] = "2000-01-01T00:00:00+00:00"
    store.upsert_entry(
        db_session,
        version_id,
        "metric.net_sales",
        "metric",
        "Net sales",
        "Net sales",
        details,
        "checked",
        [{"type": "structure", "text": "seed"}],
        "seed",
    )
    db_session.commit()


def _ready(db_session, version_id: int) -> None:
    db_session.get(KbVersion, version_id).readiness = {
        "numbers_checked": 1,
        "numbers_total": 1,
        "numbers_waiting": 0,
        "practice_right": 0,
        "practice_total": 0,
        "weak_area": None,
        "weak_area_why": "seed",
    }
    db_session.commit()


def _finish_run(db_session, version_id: int) -> None:
    db_session.add(LearningRun(kind="first", status="done", step="", version_id=version_id))
    db_session.commit()


def test_setup_atomic(db_session, version_id, learner_client) -> None:
    log_in(learner_client)
    response = learner_client.post("/api/setup/finish", json={})
    assert response.status_code == 409
    assert response.json()["error"] == "finish_first_run"
    _finish_run(db_session, version_id)
    response = learner_client.post("/api/setup/finish", json={})
    assert response.status_code == 409
    assert response.json()["error"] == "finish_not_ready"
    _seed_big(db_session, version_id)
    _ready(db_session, version_id)
    refused = learner_client.post("/api/versions/1/publish")
    assert refused.status_code == 409
    assert refused.json()["error"] == "failed_checks"
    response = learner_client.post("/api/setup/finish", json={})
    assert response.status_code == 409
    assert response.json()["error"] == "failed_checks"
    assert db_session.get(KbVersion, version_id).status == "draft"
    from charie.shared.settings import get_setting

    assert get_setting(db_session, "setup_done") is False
    assert db_session.query(KbVersion).filter_by(status="published").count() == 0


def test_concurrent_single_published(db_session, version_id) -> None:
    _seed_small(db_session, version_id)

    def publish(_: int):
        with session_scope() as session:
            return versions.publish_version(session, version_id).number

    with ThreadPoolExecutor(max_workers=4) as pool:
        numbers = list(pool.map(publish, range(4)))
    assert numbers == [1, 1, 1, 1]
    with session_scope() as session:
        live = session.query(KbVersion).filter_by(status="published").all()
        assert len(live) == 1
        assert live[0].number == 1


def test_active_chat_pinned(db_session, version_id) -> None:
    _seed_small(db_session, version_id)
    first = versions.publish_version(db_session, version_id)
    db_session.commit()
    chat = Chat(title="Sales check")
    db_session.add(chat)
    db_session.flush()
    db_session.add(
        Message(
            chat_id=chat.id,
            role="user",
            text_="What were net sales?",
            kb_version_id=first.id,
        )
    )
    db_session.commit()
    message_id = db_session.scalar(select(Message.id).limit(1))
    second = versions.get_or_create_draft(db_session, "refresh")
    _seed_small(db_session, second.id)
    versions.publish_version(db_session, second.id)
    db_session.commit()
    message = db_session.get(Message, message_id)
    assert message.kb_version_id == first.id
    assert db_session.get(KbVersion, first.id).status == "archived"
    assert db_session.get(KbVersion, second.id).status == "published"


def test_waiting_draft_not_auto(db_session, version_id) -> None:
    _seed_small(db_session, version_id)
    from charie.shared.settings import set_setting

    set_setting(db_session, "setup_done", True)
    draft = db_session.get(KbVersion, version_id)
    draft.made_by = "owner_edit"
    draft.readiness = {
        "numbers_checked": 0,
        "numbers_total": 0,
        "numbers_waiting": 0,
        "practice_right": 0,
        "practice_total": 0,
        "weak_area": None,
        "weak_area_why": "seed",
    }
    db_session.commit()
    decision = versions.finalize_run(db_session, version_id)
    assert decision == {
        "published": False,
        "version": 1,
        "reason": "A waiting owner draft stays for review.",
    }
    assert db_session.get(KbVersion, version_id).status == "draft"
    _seed_big(db_session, version_id)
    draft.made_by = "first_learning"
    db_session.commit()
    decision = versions.finalize_run(db_session, version_id)
    assert decision["published"] is False
    assert "big change" in decision["reason"]


def test_reviewed_big_change_publishes_but_not_automatically(
    db_session, version_id, learner_client
) -> None:
    """Owner review publishes a passing big change; auto-publish still waits."""
    from charie.shared.settings import set_setting

    log_in(learner_client)
    _seed_big_passing(db_session, version_id)
    set_setting(db_session, "setup_done", True)
    db_session.commit()
    decision = versions.finalize_run(db_session, version_id)
    assert decision["published"] is False
    assert "big change" in decision["reason"]
    assert db_session.get(KbVersion, version_id).status == "draft"
    response = learner_client.post("/api/versions/1/publish")
    assert response.status_code == 200
    assert db_session.get(KbVersion, version_id).status == "published"


def test_passing_first_run_reviews_publishes_and_finishes(
    db_session, version_id, learner_client
) -> None:
    """First run done, review changes, publish, then setup finishes."""
    log_in(learner_client)
    _seed_big_passing(db_session, version_id)
    _ready(db_session, version_id)
    _finish_run(db_session, version_id)
    seen = learner_client.get("/api/versions/1/changes")
    assert seen.status_code == 200
    response = learner_client.post("/api/setup/finish", json={})
    assert response.status_code == 200
    assert response.json() == {"setup_done": True}
    assert db_session.get(KbVersion, version_id).status == "published"
    from charie.shared.settings import get_setting

    assert get_setting(db_session, "setup_done") is True
