"""Checked details shapes, one model per kind (P07.3)."""

import pytest
from pydantic import ValidationError

from charie.shared.knowledge.details import DETAILS_MODELS, check_details
from charie.shared.tables.knowledge import ENTRY_KINDS

MINIMAL = {
    "table": {"schema": "public", "name": "orders"},
    "column": {"schema": "public", "table": "orders", "name": "total_amount"},
    "link": {
        "from_table": "public.orders",
        "from_columns": ["restaurant_id"],
        "to_table": "public.restaurants",
        "to_columns": ["id"],
    },
    "data_range": {
        "table": "public.orders",
        "date_column": "ordered_at",
        "date_from": "2024-01-01",
        "date_to": "2024-12-31",
    },
    "rule": {"rule_type": "currency", "currency": "USD"},
    "style": {},
    "name": {"table": "public.restaurants", "id_column": "id", "name_column": "name"},
    "metric": {
        "kind": "simple",
        "table": "shop.orders",
        "aggregate": "sum",
        "expression": "orders.total_amount",
        "time_column": "orders.created_at",
        "time_column_type": "timestamptz",
        "steps_in_words": ["Add up the orders.", "Only completed ones count."],
    },
    "dimension": {"kind": "attribute", "table": "shop.orders", "column": "status"},
    "code": {},
    "event": {},
    "data_problem": {},
    "default": {},
    "calendar": {},
    "how_to": {},
    "example": {},
}


def test_every_kind_has_a_model() -> None:
    kinds = [kind.strip("' ") for kind in ENTRY_KINDS.split(",")]
    assert set(DETAILS_MODELS) == set(kinds)
    for kind, minimal in MINIMAL.items():
        checked = check_details(kind, dict(minimal))
        assert isinstance(checked, dict)


def test_bad_details_are_refused() -> None:
    with pytest.raises(ValidationError):
        check_details("column", {"schema": "public", "table": "t", "bogus": 1})
    with pytest.raises(ValidationError):
        check_details("rule", {"rule_type": "not_a_rule"})
    with pytest.raises(ValueError, match="Unknown knowledge kind"):
        check_details("recipe", {})
    with pytest.raises(ValidationError):
        check_details("table", {"name": "orders"})
    with pytest.raises(ValueError, match="must be a mapping"):
        check_details("table", None)


def test_later_kinds_accept_extra_fields() -> None:
    checked = check_details(
        "event",
        {"tables": ["public.orders"], "happened": "the rush", "unit": "money"},
    )
    assert checked["happened"] == "the rush"
    assert checked["unit"] == "money"
    assert checked["columns"] == []


def test_metric_and_dimension_refuse_extra_fields() -> None:
    with pytest.raises(ValidationError):
        check_details(
            "metric",
            {
                "kind": "simple",
                "table": "shop.orders",
                "aggregate": "sum",
                "expression": "orders.total_amount",
                "time_column": "orders.created_at",
                "time_column_type": "timestamptz",
                "steps_in_words": ["Add up the orders.", "Only completed ones count."],
                "bogus": 1,
            },
        )
    with pytest.raises(ValidationError):
        check_details(
            "dimension",
            {"kind": "attribute", "table": "shop.orders", "column": "status", "bogus": 1},
        )
