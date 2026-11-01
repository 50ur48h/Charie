"""Ways A and B stay independent: different guidance, no query leaks (P10.7)."""

import json

from charie.chat.analyst.helpers.new_number import brief_input
from charie.shared.knowledge.sql_writer import brief_for_way


def _brief() -> dict:
    return {
        "input": brief_input(
            question="How many shop orders are there?",
            scope_table="shop.orders",
            time_column="",
            time_zone="America/Chicago",
            splits=[],
            period_start="2025-12-01",
            period_end="2025-12-31",
            structure="shop.orders(id, created_on).",
        ),
        "catalog": {"tables": ["shop.orders"]},
    }


def test_way_instructions_differ() -> None:
    """Way A and way B get different approach lines."""
    brief = _brief()
    assert brief_for_way(brief, "A")["input"]["way_guidance"] == "Use Way A."
    assert brief_for_way(brief, "B")["input"]["way_guidance"] == "Use Way B."
    assert brief_for_way(brief, "")["input"]["way_guidance"] == ""


def test_way_b_input_has_no_way_a_query() -> None:
    """Way B's brief is built from the task, never from way A's answer."""
    sql_a = "SELECT COUNT(*) AS value FROM shop.orders AS orders"
    guided_b = brief_for_way(_brief(), "B")
    shown = json.dumps(guided_b["input"], sort_keys=True)
    assert sql_a not in shown
    assert "shop.orders(id, created_on)." in shown
