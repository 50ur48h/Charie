"""GET/PUT /api/owner-notes and the sorted columns (P07.5)."""

from charie.shared.db import session_scope
from charie.shared.knowledge import store, versions
from tests.conftest import log_in


def _entries() -> None:
    """A draft with owner-notes entries: one rule, one style, one hint."""
    with session_scope() as session:
        draft = versions.get_or_create_draft(session, "first_learning")
        store.upsert_entry(
            session,
            draft.id,
            "rule.no_orders_old",
            "rule",
            "Never use orders_old",
            "Never use the table orders_old.",
            {"rule_type": "never_use_table", "table": "public.orders_old"},
            "confirmed",
            [{"type": "owner_notes", "quote": "Never use orders_old"}],
            "Sorting the owner notes",
        )
        store.upsert_entry(
            session,
            draft.id,
            "style.profit_note",
            "style",
            "Add the profit note",
            "Add the profit note.",
            {"topics": ["profit"]},
            "confirmed",
            [{"type": "owner_notes", "quote": "Add the profit note"}],
            "Sorting the owner notes",
        )
        store.upsert_entry(
            session,
            draft.id,
            "default.lunch",
            "default",
            "Lunch",
            "Orders placed between 11 am and 3 pm.",
            {},
            "confirmed",
            [{"type": "owner_notes", "quote": "Lunch is 11 to 3"}],
            "Sorting the owner notes",
        )
        session.commit()


def test_no_notes_yet(learner_client, db) -> None:
    log_in(learner_client)
    response = learner_client.get("/api/owner-notes")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "text": "",
        "saved_at": None,
        "lines": 0,
        "sorted": None,
        "sorted_at": None,
    }


def test_put_saves_a_new_row_only_when_changed(learner_client, db) -> None:
    log_in(learner_client)
    first = learner_client.put(
        "/api/owner-notes", json={"text": "Money is in USD.\n\nNever convert.\n"}
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["text"] == "Money is in USD.\n\nNever convert.\n"
    assert body["lines"] == 2
    assert body["saved_at"] is not None
    again = learner_client.put(
        "/api/owner-notes", json={"text": "Money is in USD.\n\nNever convert.\n"}
    )
    assert again.json()["saved_at"] == body["saved_at"]
    with session_scope() as session:
        from sqlalchemy import func, select

        from charie.shared.tables.sources import OwnerNote

        assert session.scalar(select(func.count()).select_from(OwnerNote)) == 1
    changed = learner_client.put("/api/owner-notes", json={"text": "Money is in USD."})
    assert changed.json()["text"] == "Money is in USD."
    assert changed.json()["lines"] == 1
    with session_scope() as session:
        from sqlalchemy import func, select

        from charie.shared.tables.sources import OwnerNote

        assert session.scalar(select(func.count()).select_from(OwnerNote)) == 2


def test_notes_too_long(learner_client, db) -> None:
    log_in(learner_client)
    response = learner_client.put("/api/owner-notes", json={"text": "x" * 100_001})
    assert response.status_code == 400
    assert response.json() == {
        "error": "notes_too_long",
        "message": "Your notes are too long. Keep them under 100,000 characters.",
    }


def test_sorted_lists_come_from_entries(learner_client, db) -> None:
    _entries()
    log_in(learner_client)
    learner_client.put(
        "/api/owner-notes",
        json={"text": "Never use orders_old.\nAdd the profit note.\nLunch is 11 to 3.\n"},
    )
    body = learner_client.get("/api/owner-notes").json()
    assert body["lines"] == 3
    assert body["sorted"] == {
        "hard_rules": [{"key": "rule.no_orders_old", "title": "Never use orders_old"}],
        "style": [{"key": "style.profit_note", "title": "Add the profit note"}],
        "hints": [{"key": "default.lunch", "title": "Lunch"}],
    }


def test_owner_notes_need_login(learner_client, db) -> None:
    assert learner_client.get("/api/owner-notes").status_code == 401
    assert learner_client.put("/api/owner-notes", json={"text": "x"}).status_code == 401
