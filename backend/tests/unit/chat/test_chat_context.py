"""The chat context: model, section text and the update rules (P11.1)."""

import json
from pathlib import Path

from charie.chat.analyst.chat_context import (
    ChatContext,
    FinishedAnswer,
    Focus,
    OpenReason,
    SaidFact,
    ShownList,
    context_for_prompt,
    fact_key_text,
    load_context,
    save_context,
    update_context,
)

DATA = Path(__file__).parent / "data"


def _december() -> FinishedAnswer:
    """A done December answer: two numbers, one restaurant table, one reason."""
    orders_key = {
        "metric": "order_count",
        "filters": [],
        "split": {},
        "period": "2025-12-01/2025-12-31",
        "compare_period": "",
        "measure": "value",
    }
    sales_key = {
        "metric": "net_sales",
        "filters": [],
        "split": {},
        "period": "2025-12-01/2025-12-31",
        "compare_period": "",
        "measure": "value",
    }
    return FinishedAnswer(
        message_id=7,
        question="How did December go?",
        kind="clear",
        asks=[
            {"kind": "total", "metric_key": "order_count", "periods": ["p1"]},
            {"kind": "total", "metric_key": "net_sales", "periods": ["p1"]},
        ],
        filters=[],
        periods=[
            {
                "label": "p1",
                "expression": {"kind": "month", "number": 12},
                "start": "2025-12-01",
                "end": "2025-12-31",
                "text": "1-31 Dec 2025",
            }
        ],
        used_labels=["n1", "n2"],
        items=[
            {
                "label": "n1",
                "kind": "number",
                "description": "Shop orders in 1-31 Dec 2025",
                "value": {"value": "25064", "unit": "count", "currency": "", "style": "value"},
                "proof": {"task": "recipe|order_count|", "fact_key": orders_key, "way": "recipe"},
            },
            {
                "label": "n2",
                "kind": "number",
                "description": "Net sales in 1-31 Dec 2025",
                "value": {
                    "value": "1354004.63",
                    "unit": "money",
                    "currency": "USD",
                    "style": "value",
                },
                "proof": {"task": "recipe|net_sales|", "fact_key": sales_key, "way": "recipe"},
            },
            {
                "label": "t1",
                "kind": "table",
                "description": "Shop orders by restaurant, 1-31 Dec 2025",
                "value": {
                    "columns": [],
                    "rows": [["Mario's", 18000], ["Luigi's", 5000], ["Peach's", 2064]],
                    "rows_total": 3,
                    "sql": "SELECT 1",
                },
                "proof": {
                    "task": "recipe|order_count|restaurant|",
                    "split_by": ["restaurant"],
                    "fact_key": orders_key,
                    "way": "recipe",
                },
            },
        ],
        draft={
            "blocks": [
                {
                    "type": "text",
                    "sentences": [
                        {
                            "kind": "fact",
                            "text": "Shop orders were [n1].",
                            "proof": ["n1"],
                            "starts_paragraph": True,
                        },
                        {
                            "kind": "possible_reason",
                            "text": "Holiday catering may explain the jump [n1].",
                            "proof": ["n1"],
                            "starts_paragraph": False,
                        },
                    ],
                },
                {
                    "type": "table",
                    "table": {"table": "t1", "title": "Orders by restaurant", "columns_shown": []},
                },
            ]
        },
        blocks=[
            {
                "type": "text",
                "paragraphs": [
                    {"sentences": [{"kind": "fact", "text": "Shop orders were 25.1K."}]}
                ],
            },
            {
                "type": "table",
                "title": "Orders by restaurant",
                "columns": [
                    {"key": "name", "label": "Restaurant"},
                    {"key": "value", "label": "Orders"},
                ],
                "rows": [
                    {"name": "Mario's", "value": 18000},
                    {"name": "Luigi's", "value": 5000},
                    {"name": "Peach's", "value": 2064},
                ],
            },
        ],
        data_through="2025-12-31",
        kb_version=2,
        style="short",
    )


def test_context_after_december() -> None:
    """The December answer folds into context exactly as the fixture says."""
    context = update_context(ChatContext(), _december())
    expected = json.loads((DATA / "context_after_december.json").read_text(encoding="utf-8"))
    assert context.model_dump() == expected


def test_proof_key_carries_over_without_fact_key() -> None:
    """A rerun without proof keeps the earlier key; a new number gets one."""
    first = update_context(ChatContext(), _december())
    rerun = _december()
    rerun.message_id = 8
    rerun.items[0]["proof"] = {"task": "recipe|order_count|", "way": "recipe"}
    rerun.items.append(
        {
            "label": "n3",
            "kind": "number",
            "description": "Average order value in 1-31 Dec 2025",
            "value": {"value": "54.02", "unit": "money", "currency": "USD", "style": "value"},
            "proof": {
                "task": "recipe|aov|",
                "fact_key": {
                    "metric": "aov",
                    "filters": [],
                    "split": {},
                    "period": "2025-12-01/2025-12-31",
                    "compare_period": "",
                    "measure": "value",
                },
                "way": "recipe",
            },
        }
    )
    rerun.used_labels = ["n1", "n3"]
    second = update_context(first, rerun)
    by_ref = {fact.ref: fact for fact in second.said}
    assert by_ref["8:n1"].key == fact_key_text(_december().items[0])
    assert by_ref["8:n3"].key != "{}"


def test_two_answers_keep_their_own_n1() -> None:
    """Two messages using n1 for different facts both stay available."""
    from charie.chat.analyst.about import _parse_about_refs
    from charie.chat.analyst.checks import _said_numbers

    first = update_context(ChatContext(), _december())
    rerun = _december()
    rerun.message_id = 8
    rerun.used_labels = ["n1"]
    net_sales = dict(rerun.items[1])
    net_sales["label"] = "n1"
    rerun.items = [net_sales]
    context = update_context(first, rerun)
    assert [fact.ref for fact in context.said] == ["7:n1", "7:n2", "8:n1"]
    by_ref = {fact.ref: fact for fact in context.said}
    assert by_ref["7:n1"].description == "Shop orders in 1-31 Dec 2025"
    assert by_ref["8:n1"].description == "Net sales in 1-31 Dec 2025"
    assert by_ref["7:n1"].key != by_ref["8:n1"].key
    numbers = _said_numbers(context.said)
    assert [entry["fact_key"]["metric"] for entry in numbers] == [
        "order_count",
        "net_sales",
        "net_sales",
    ]
    assert [entry["message_id"] for entry in numbers] == [7, 7, 8]
    view = context_for_prompt(context)
    assert "[7:n1] Shop orders in 1-31 Dec 2025 = 25.1K;" in view
    assert "[8:n1] Net sales in 1-31 Dec 2025 = $1.35M;" in view
    assert _parse_about_refs(["7:n1", "8:n1"]) == [(7, "n1"), (8, "n1")]


def test_lists_keep_newest_three_and_find_dimension() -> None:
    """Lists cap at three; the dimension is the table's first split."""
    context = ChatContext()
    for turn in range(5):
        finished = _december()
        finished.message_id = 10 + turn
        finished.blocks[1]["title"] = f"Orders by restaurant, run {turn}"
        context = update_context(context, finished)
    assert [shown.title for shown in context.lists] == [
        f"Orders by restaurant, run {turn}" for turn in (2, 3, 4)
    ]
    assert all(shown.dimension == "restaurant" for shown in context.lists)
    assert len(context.said) == 10
    assert [fact.ref for fact in context.said] == [
        "10:n1",
        "10:n2",
        "11:n1",
        "11:n2",
        "12:n1",
        "12:n2",
        "13:n1",
        "13:n2",
        "14:n1",
        "14:n2",
    ]


def test_save_and_reload_agree(db_session) -> None:
    """The JSON on the chat row round-trips through save and load."""
    from charie.shared.tables.chat import Chat

    chat = Chat(title="Ctx", private=True)
    db_session.add(chat)
    db_session.commit()
    save_context(db_session, chat.id, update_context(ChatContext(), _december()))
    db_session.commit()
    assert load_context(db_session, chat.id) == update_context(ChatContext(), _december())
    assert load_context(db_session, 10**9) == ChatContext()


def test_empty_context_gives_an_empty_view() -> None:
    """No memory means no prompt text."""
    assert context_for_prompt(ChatContext()) == ""


def test_context_view_numbers_the_newest_list_first() -> None:
    """The prompt sees the newest list as List 1, with focus, facts, reasons."""
    context = ChatContext(
        focus=Focus(
            message_id=7,
            question="Net sales?",
            kind="clear",
            asks=[{"metric_key": "net_sales", "new_metric": "", "split_by": [], "top_n": None}],
            filters=[],
            periods=[
                {
                    "label": "p1",
                    "expression": {},
                    "start": "2025-12-01",
                    "end": "2025-12-31",
                    "text": "1–31 Dec 2025",
                }
            ],
        ),
        lists=[
            ShownList(message_id=7, title="Older list", dimension="cuisine", items=["Italian"]),
            ShownList(
                message_id=8,
                title="Sales by restaurant",
                dimension="restaurant",
                items=["Downtown Austin", "Rice, Miller and Gutmann"],
            ),
        ],
        said=[
            SaidFact(
                ref="7:n1",
                key="{}",
                description="Net sales",
                text="$1.3M",
                value="1300000",
                unit="money",
                currency="USD",
                data_through="2025-12-31",
                kb_version=2,
            )
        ],
        open_reasons=[OpenReason(message_id=8, text="The south branch closed.", labels=[])],
    )
    view = context_for_prompt(context)
    assert "Looking at: net sales; 1–31 Dec 2025" in view
    first = view.index('List 1 (newest), "Sales by restaurant"')
    second = view.index('List 2, "Older list"')
    assert first < second
    assert "1. Downtown Austin 2. Rice, Miller and Gutmann" in view
    assert "Already said: [7:n1] Net sales = $1.3M;" in view
    assert "Possible reasons still open: The south branch closed." in view
