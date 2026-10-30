"""`GET /api/knowledge` in both apps, Learner PATCH/approve/wrong (P07.4)."""

import pytest
from sqlalchemy import select

from charie.shared.db import session_scope
from charie.shared.knowledge import store, versions
from charie.shared.tables.knowledge import KbChange
from tests.conftest import log_in

TABLE_DETAILS = {"schema": "public", "name": "orders"}
COLUMN_DETAILS = {"schema": "public", "table": "orders", "name": "total_amount"}
LINK_DETAILS = {
    "from_table": "public.orders",
    "from_columns": ["restaurant_id"],
    "to_table": "public.restaurants",
    "to_columns": ["id"],
}
RANGE_DETAILS = {
    "table": "public.orders",
    "date_column": "created_at",
    "date_from": "2024-01-01",
    "date_to": "2025-12-31",
    "exact": True,
    "columns": [],
}
LONG_MEANING = "Meaning. " * 40  # 360 characters: the list cuts it to 200.


def _seed_published() -> int:
    """Version 1 with one entry of each listed kind, published directly."""
    with session_scope() as session:
        draft = versions.get_or_create_draft(session, "first_learning")
        store.upsert_entry(
            session,
            draft.id,
            "table.public.orders",
            "table",
            "orders",
            "A table with about 400K rows and 9 columns.",
            TABLE_DETAILS,
            "checked",
            [{"type": "structure", "text": "Read from the database structure"}],
            "First learning",
        )
        store.upsert_entry(
            session,
            draft.id,
            "column.public.orders.total_amount",
            "column",
            "orders.total_amount",
            LONG_MEANING,
            COLUMN_DETAILS,
            "guessed",
            [{"type": "profile", "text": "Measured from the data"}],
            "First learning",
        )
        store.upsert_entry(
            session,
            draft.id,
            "rule.no_orders_old",
            "rule",
            "Never use orders_old",
            "Never use the table orders_old.",
            {"rule_type": "never_use_table", "table": "public.orders_old"},
            "conflicting",
            [{"type": "owner_notes", "quote": "Never use orders_old"}],
            "First learning",
        )
        draft.number = 1
        draft.status = "published"
        session.commit()
        return draft.id


@pytest.fixture
def published(db) -> int:
    return _seed_published()


def _learner(learner_client):
    log_in(learner_client)
    return learner_client


def test_published_entry_shows_in_both_apps(learner_client, chat_client, published) -> None:
    for client in (learner_client, chat_client):
        log_in(client)
        response = client.get("/api/knowledge")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["version"]["number"] == 1
        assert body["version"]["status"] == "published"
        assert body["needs_review"] == 2
        assert body["counts"]["table"] == 1
        assert body["counts"]["metric"] == 0
        row = next(entry for entry in body["entries"] if entry["key"] == "table.public.orders")
        assert row["title"] == "orders"
        assert set(row) == {"key", "kind", "title", "meaning", "confidence", "updated_at"}
        long_row = next(
            entry
            for entry in body["entries"]
            if entry["key"] == "column.public.orders.total_amount"
        )
        assert len(long_row["meaning"]) <= 200
        detail = client.get("/api/knowledge/table.public.orders").json()
        assert detail["entry"]["meaning"].startswith("A table with about 400K rows")
        assert detail["version"]["number"] == 1
        assert detail["history"][0]["change"] == "added"


def test_chat_app_refuses_draft(learner_client, chat_client, published) -> None:
    log_in(chat_client)
    response = chat_client.get("/api/knowledge", params={"version": "draft"})
    assert response.status_code == 400
    assert response.json() == {
        "error": "bad_version",
        "message": "The chat app only shows the published knowledge.",
    }
    entry = chat_client.get("/api/knowledge/table.public.orders", params={"version": "draft"})
    assert entry.status_code == 400


def test_learner_draft_falls_back_to_published(learner_client, published) -> None:
    log_in(learner_client)
    body = learner_client.get("/api/knowledge", params={"version": "draft"}).json()
    assert body["version"]["status"] == "published"
    assert len(body["entries"]) == 3


def test_kind_and_words_filters(learner_client, published) -> None:
    log_in(learner_client)
    only_tables = learner_client.get("/api/knowledge", params={"kind": "table"}).json()
    assert [entry["key"] for entry in only_tables["entries"]] == ["table.public.orders"]
    both = learner_client.get("/api/knowledge", params={"kind": "table,column"}).json()
    assert len(both["entries"]) == 2
    words = learner_client.get("/api/knowledge", params={"q": "400K rows"}).json()
    assert [entry["key"] for entry in words["entries"]] == ["table.public.orders"]
    bad = learner_client.get("/api/knowledge", params={"kind": "number"})
    assert bad.status_code == 400
    assert bad.json()["error"] == "bad_kind"


def test_unknown_key_is_404(learner_client, published) -> None:
    log_in(learner_client)
    response = learner_client.get("/api/knowledge/no.such.key")
    assert response.status_code == 404
    assert response.json() == {
        "error": "not_found",
        "message": "There's no knowledge entry called no.such.key.",
    }


def test_patch_records_a_change(learner_client, published) -> None:
    log_in(learner_client)
    response = learner_client.patch(
        "/api/knowledge/table.public.orders", json={"meaning": "Orders, fixed by you."}
    )
    assert response.status_code == 200, response.text
    assert response.json()["entry"]["meaning"] == "Orders, fixed by you."
    with session_scope() as session:
        draft = versions.get_draft(session)
        assert draft is not None and draft.made_by == "owner_edit"
        entry = store.get_entry(session, draft.id, "table.public.orders")
        assert entry is not None
        assert entry.confidence == "confirmed"
        assert any(
            source.get("type") == "owner_edit" and source.get("text") == "Edited by you"
            for source in entry.sources
        )
    draft_body = learner_client.get("/api/knowledge", params={"version": "draft"}).json()
    assert draft_body["version"]["status"] == "draft"
    assert draft_body["version"]["changes"] == 1
    detail = learner_client.get(
        "/api/knowledge/table.public.orders", params={"version": "draft"}
    ).json()
    edits = [row for row in detail["history"] if row["change"] == "changed"]
    assert len(edits) == 1
    assert edits[0]["reason"] == "Edited by you"
    with session_scope() as session:
        draft = versions.get_draft(session)
        assert draft is not None
        rows = session.scalars(
            select(KbChange).where(KbChange.version_id == draft.id, KbChange.change == "changed")
        ).all()
        assert len(rows) == 1
        assert rows[0].before["meaning"] != "Orders, fixed by you."
        assert rows[0].after["meaning"] == "Orders, fixed by you."


def test_patch_validation(learner_client, published) -> None:
    log_in(learner_client)
    assert learner_client.patch("/api/knowledge/table.public.orders", json={}).status_code == 400
    empty = learner_client.patch("/api/knowledge/table.public.orders", json={"title": "  "})
    assert empty.status_code == 400
    assert empty.json()["message"] == "The title can't be empty."
    long = learner_client.patch("/api/knowledge/table.public.orders", json={"title": "T" * 201})
    assert long.status_code == 400
    too_long = learner_client.patch(
        "/api/knowledge/table.public.orders", json={"meaning": "M" * 2001}
    )
    assert too_long.status_code == 400
    assert too_long.json()["message"] == "The meaning is too long. Keep it under 2,000 characters."
    missing = learner_client.patch("/api/knowledge/no.such.key", json={"title": "X"})
    assert missing.status_code == 404


def test_mark_wrong_adds_a_todo(learner_client, published) -> None:
    log_in(learner_client)
    response = learner_client.post(
        "/api/knowledge/table.public.orders/wrong", json={"note": "Counts look double."}
    )
    assert response.status_code == 201, response.text
    assert response.json()["todo"]["text"] == "orders: Counts look double."
    assert response.json()["todo"]["kind"] == "correction"
    todos = learner_client.get("/api/todos").json()["todos"]
    assert [todo["text"] for todo in todos] == ["orders: Counts look double."]
    assert todos[0]["details"]["key"] == "table.public.orders"
    # The entry and the draft stay untouched: still no draft, still checked.
    with session_scope() as session:
        assert versions.get_draft(session) is None
        published_version = versions.get_published(session)
        assert published_version is not None
        entry = store.get_entry(session, published_version.id, "table.public.orders")
        assert entry is not None and entry.confidence == "checked"
    missing = learner_client.post("/api/knowledge/no.such.key/wrong", json={})
    assert missing.status_code == 404


def test_approve_sets_confirmed(learner_client, published) -> None:
    log_in(learner_client)
    key = "column.public.orders.total_amount"
    response = learner_client.post(f"/api/knowledge/{key}/approve")
    assert response.status_code == 200, response.text
    assert response.json()["entry"]["confidence"] == "confirmed"
    again = learner_client.post(f"/api/knowledge/{key}/approve")
    assert again.status_code == 409
    assert again.json()["error"] == "nothing_to_approve"


def test_knowledge_needs_login(learner_client, chat_client, published) -> None:
    assert learner_client.get("/api/knowledge").status_code == 401
    assert chat_client.get("/api/knowledge").status_code == 401
    assert learner_client.get("/api/todos").status_code == 401
