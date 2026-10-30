"""Draft versions copy the published entries (P07.3)."""

from sqlalchemy import func, select

from charie.shared.db import session_scope
from charie.shared.knowledge import store, versions
from charie.shared.tables.knowledge import KbChange, KbEntry, KbVersion


def test_first_draft_starts_empty(db) -> None:
    with session_scope() as session:
        draft = versions.get_or_create_draft(session, "first_learning")
        assert draft.status == "draft"
        assert draft.number == 1
        assert session.scalar(select(func.count()).select_from(KbEntry)) == 0
        assert versions.get_draft(session).id == draft.id
        assert versions.get_published(session) is None


def test_new_draft_copies_published_entries(db) -> None:
    with session_scope() as session:
        first = versions.get_or_create_draft(session, "first_learning")
        store.upsert_entry(
            session,
            first.id,
            "table.public.orders",
            "table",
            "Orders",
            "One row per order.",
            {"schema": "public", "name": "orders"},
            "checked",
            [{"type": "structure"}],
            "Studying the structure.",
        )
        first.status = "published"
    with session_scope() as session:
        published = versions.get_published(session)
        assert published is not None
        before = session.scalar(select(func.count()).select_from(KbChange))
        draft = versions.get_or_create_draft(session, "refresh")
        assert draft.number == 2
        assert versions.get_published(session).id == published.id
        copied = store.get_entry(session, draft.id, "table.public.orders")
        assert copied is not None
        assert copied.title == "Orders"
        assert copied.details["schema"] == "public"
        assert copied.details["name"] == "orders"
        assert [source["type"] for source in copied.sources] == ["structure"]
        assert copied.id != store.get_entry(session, published.id, "table.public.orders").id
        assert session.scalar(select(func.count()).select_from(KbChange)) == before


def test_only_one_draft_at_a_time(db) -> None:
    with session_scope() as session:
        first = versions.get_or_create_draft(session, "first_learning")
        again = versions.get_or_create_draft(session, "refresh")
        assert again.id == first.id
        assert session.scalar(select(func.count()).select_from(KbVersion)) == 1
