"""The understanding form, inputs and checks (P10.4)."""

from datetime import date

from charie.chat.analyst import understand as understand_module
from charie.chat.analyst.dates import PeriodExpression
from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.understand import (
    Ask,
    Filter,
    Understanding,
    check_understanding,
    knowledge_summary,
    understand_input,
)
from charie.shared.ai.forms import form_schema
from charie.shared.ai.prompts import build_messages, load_prompt


def _kb() -> KbView:
    entries = {
        "metric": {"net_sales": {"kind": "sum"}},
        "dimension": {"cuisine": {"table": "restaurants", "column": "cuisine"}},
        "default": {
            "sales": {"word": "sales", "value": "net_sales"},
            "last_week": {"word": "last week", "value": "last_full_week"},
        },
        "name": {
            "restaurant": {
                "table": "restaurants",
                "items": [{"id": 1, "name": "Downtown"}, {"id": 2, "name": "MEGA0926"}],
            }
        },
        "calendar": {"cal": {"week_start": "monday", "fiscal_year_start": 1}},
    }
    texts = {
        "net_sales": {"title": "Net sales", "meaning": "Order totals minus refunds."},
        "cuisine": {"title": "Cuisine", "meaning": "The kind of food."},
        "sales": {"title": "Sales", "meaning": "Vague word for sales."},
        "last_week": {"title": "Last week", "meaning": "Vague word for last week."},
        "restaurant": {"title": "Restaurant", "meaning": "Where the food is sold."},
        "cal": {"title": "Calendar", "meaning": "Business calendar."},
    }
    return KbView(entries, {}, date(2025, 12, 31), texts)


def _good_reply() -> Understanding:
    return Understanding(
        kind="clear",
        reading="I read this as **net sales** for [p1].",
        periods=[PeriodExpression(kind="month", number=12)],
        asks=[Ask(metric_key="net_sales")],
        filters=[],
        defaults_used=[],
        document_topics=[],
    )


def test_form_has_no_self_reference() -> None:
    form_schema(Understanding)


def test_input_puts_stable_parts_first() -> None:
    prompt = load_prompt("understand_question")
    inputs = {
        "question": "Net sales in December 2025",
        "anchor": "2025-12-31",
        "data_through": "2025-12-31",
        "earlier": [],
        "memories": [],
        "repair": "",
    }
    messages = build_messages(prompt, inputs, knowledge_summary="KNOWLEDGE")
    assert [message["role"] for message in messages] == ["system", "user"]
    system, user = (message["content"] for message in messages)
    assert "KNOWLEDGE" in system
    assert system.index("never type numbers") < system.index("## What Charie knows")
    assert "Net sales in December 2025" in user


def test_understand_input_keys(monkeypatch) -> None:
    class _Rows:
        def all(self):
            return []

    class _Session:
        def scalars(self, stmt):
            return _Rows()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(understand_module, "session_scope", lambda: _Session())
    monkeypatch.setattr(understand_module, "get_setting", lambda session, key: "")

    class _Ctx:
        chat_id = 1
        question = "Net sales?"

    inputs = understand_input(_Ctx(), _kb())
    assert inputs["question"] == "Net sales?"
    assert inputs["data_through"] == "2025-12-31"
    assert inputs["earlier"] == []
    assert inputs["memories"] == []
    assert inputs["repair"] == ""


def test_check_accepts_good_reply() -> None:
    assert check_understanding(_good_reply(), _kb()) == []


def test_unknown_metric_is_a_problem() -> None:
    reply = _good_reply()
    reply.asks = [Ask(metric_key="nope")]
    problems = check_understanding(reply, _kb())
    assert any("nope" in problem for problem in problems)


def test_unknown_split_is_a_problem() -> None:
    reply = _good_reply()
    reply.asks = [Ask(metric_key="net_sales", split_by=["nope"])]
    assert check_understanding(reply, _kb()) != []


def test_unknown_filter_value_is_a_problem() -> None:
    reply = _good_reply()
    reply.filters = [Filter(dimension_key="cuisine", values=["Uptown"])]
    problems = check_understanding(reply, _kb())
    assert any("Uptown" in problem for problem in problems)


def test_filter_value_fixed_to_stored_spelling() -> None:
    reply = _good_reply()
    reply.filters = [Filter(dimension_key="cuisine", values=["downtown"])]
    assert check_understanding(reply, _kb()) == []
    assert reply.filters[0].values == ["Downtown"]


def test_reading_with_digits_is_a_problem() -> None:
    reply = _good_reply()
    reply.reading = "I read this as net sales of 42 for [p1]."
    problems = check_understanding(reply, _kb())
    assert any("42" in problem for problem in problems)


def test_reading_with_unknown_label_is_a_problem() -> None:
    reply = _good_reply()
    reply.reading = "I read this as net sales for [p9]."
    assert check_understanding(reply, _kb()) != []


def test_knowledge_summary_lists_everything() -> None:
    summary = knowledge_summary(_kb())
    assert "net_sales" in summary
    assert "cuisine" in summary
    assert "default.sales" in summary
    assert "Downtown" in summary


def test_mixed_token_in_reading_allowed_when_known() -> None:
    reply = _good_reply()
    reply.reading = "I read this as MEGA0926 sales for [p1]."
    assert check_understanding(reply, _kb()) == []
