"""Link candidates from foreign keys and matching names (P07.8)."""

from charie.learner.steps.links import find_candidates


def _tables() -> dict:
    return {
        "shop.orders": {
            "is_view": False,
            "primary_key": ["id"],
            "foreign_keys": [
                {
                    "columns": ["store_id"],
                    "ref_table": "shop.stores",
                    "ref_columns": ["id"],
                }
            ],
        },
        "shop.stores": {"is_view": False, "primary_key": ["id"], "foreign_keys": []},
        "shop.restaurants": {"is_view": False, "primary_key": ["id"], "foreign_keys": []},
        "shop.categories": {"is_view": False, "primary_key": ["id"], "foreign_keys": []},
        "shop.coupons": {"is_view": False, "primary_key": ["code"], "foreign_keys": []},
        "shop.refs": {"is_view": False, "primary_key": ["code"], "foreign_keys": []},
        "shop.daily_sales": {"is_view": True, "primary_key": [], "foreign_keys": []},
    }


def _columns() -> dict:
    return {
        ("shop", "orders"): {
            "id": {"data_type": "integer"},
            "store_id": {"data_type": "integer"},
            "restaurant_id": {"data_type": "integer"},
            "category_id": {"data_type": "integer"},
            "coupon_code": {"data_type": "text"},
            "code": {"data_type": "text"},
            "note": {"data_type": "text"},
        },
        ("shop", "stores"): {"id": {"data_type": "integer"}},
        ("shop", "restaurants"): {"id": {"data_type": "integer"}},
        ("shop", "categories"): {"id": {"data_type": "integer"}},
        ("shop", "coupons"): {"code": {"data_type": "text"}},
        ("shop", "refs"): {"code": {"data_type": "integer"}},
        ("shop", "daily_sales"): {"day": {"data_type": "date"}},
    }


def _marks(candidates: list[dict]) -> set:
    return {
        (
            candidate["from_table"],
            ",".join(candidate["from_columns"]),
            candidate["to_table"],
            ",".join(candidate["to_columns"]),
            candidate["via"],
        )
        for candidate in candidates
    }


def test_foreign_keys_are_candidates() -> None:
    found = _marks(find_candidates(_tables(), _columns(), set()))
    assert ("shop.orders", "store_id", "shop.stores", "id", "fk") in found
    # The foreign key wins over the name rule: one candidate, not two.
    assert sum(1 for mark in found if mark[1] == "store_id") == 1


def test_name_rules() -> None:
    found = _marks(find_candidates(_tables(), _columns(), set()))
    assert ("shop.orders", "restaurant_id", "shop.restaurants", "id", "name") in found
    assert ("shop.orders", "category_id", "shop.categories", "id", "name") in found
    assert ("shop.orders", "coupon_code", "shop.coupons", "code", "name") in found
    # A bare `code` matches the text key, not the integer one.
    assert ("shop.orders", "code", "shop.coupons", "code", "name") in found
    assert not [mark for mark in found if mark[2] == "shop.refs"]
    # A column named just `id` is never a link on its own.
    assert not [mark for mark in found if mark[1] == "id"]
    # The text note matches no integer key.
    assert not [mark for mark in found if mark[1] == "note"]


def test_views_and_forbidden_tables_are_left_out() -> None:
    found = _marks(find_candidates(_tables(), _columns(), {"shop.stores", "shop.coupons"}))
    assert not [mark for mark in found if "daily_sales" in mark[0] or "daily_sales" in mark[2]]
    assert not [mark for mark in found if "stores" in mark[2] or "coupons" in mark[2]]
    assert not [mark for mark in found if "stores" in mark[0]]
    assert ("shop.orders", "restaurant_id", "shop.restaurants", "id", "name") in found
