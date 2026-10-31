"""Hard data rules from the catalog (P09.2).

Test restaurants stay out unless the recipe wants them: the catalog turns
the rule entry into a required filter, and the builder only applies it to
tables in the query.
"""

from charie.shared.db import session_scope
from charie.shared.knowledge import store, versions
from charie.shared.knowledge.catalog import build_catalog
from charie.shared.safety.catalog import required_filters_for


def _seed() -> int:
    with session_scope() as session:
        draft = versions.get_or_create_draft(session, "first_learning")
        store.upsert_entry(
            session,
            draft.id,
            "table.shop.orders",
            "table",
            "orders",
            "The orders table.",
            {"schema": "shop", "name": "orders"},
            "checked",
            [{"type": "structure", "text": "Read from the database structure"}],
            "seed",
        )
        store.upsert_entry(
            session,
            draft.id,
            "table.shop.restaurants",
            "table",
            "restaurants",
            "The restaurants table.",
            {"schema": "shop", "name": "restaurants"},
            "checked",
            [{"type": "structure", "text": "Read from the database structure"}],
            "seed",
        )
        store.upsert_entry(
            session,
            draft.id,
            "rule.no_test_restaurants",
            "rule",
            "No test restaurants",
            "Test restaurants never count unless asked.",
            {
                "rule_type": "always_filter",
                "table": "shop.restaurants",
                "column": "is_test",
                "values": ["false"],
            },
            "confirmed",
            [{"type": "owner_notes", "quote": "Test restaurants never count"}],
            "seed",
        )
        return draft.id


def test_hard_rule_keeps_out_test_restaurants(db) -> None:
    version_id = _seed()
    with session_scope() as session:
        catalog = build_catalog(session, version_id)
    assert required_filters_for(catalog, ["shop.restaurants"]) == ["restaurants.is_test = false"]
    assert required_filters_for(catalog, ["shop.orders"]) == []
