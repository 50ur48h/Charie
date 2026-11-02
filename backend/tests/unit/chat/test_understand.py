"""The understanding form, inputs and checks (P10.4)."""

from datetime import date

from charie.chat.analyst import understand as understand_module
from charie.chat.analyst.dates import PeriodExpression
from charie.chat.analyst.helpers.tasks import starter_tasks
from charie.chat.analyst.kb_view import KbView
from charie.chat.analyst.references import ListRef, PeriodShift
from charie.chat.analyst.understand import (
    Ask,
    Filter,
    Meaning,
    Understanding,
    apply_fallbacks,
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
        "chat_context": "",
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
        """A session that refuses work after its scope closes."""

        def __init__(self):
            self.closed = False

        def scalars(self, stmt):
            assert not self.closed, "used a closed session"
            return _Rows()

        def get(self, model, key):
            assert not self.closed, "used a closed session"
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True
            return False

    def _get_setting(session, key):
        assert not session.closed, "used a closed session"
        return key == "memory_on"

    def _memories(session):
        assert not session.closed, "used a closed session"
        return ["For me, sales means without delivery fees."]

    monkeypatch.setattr(understand_module, "session_scope", lambda: _Session())
    monkeypatch.setattr(understand_module, "get_setting", _get_setting)
    monkeypatch.setattr(understand_module, "memories_for_prompt", _memories)

    class _Ctx:
        chat_id = 1
        question = "Net sales?"

    inputs = understand_input(_Ctx(), _kb())
    assert inputs["question"] == "Net sales?"
    assert inputs["data_through"] == "2025-12-31"
    assert inputs["earlier"] == []
    assert inputs["chat_context"] == ""
    assert inputs["memories"] == ["For me, sales means without delivery fees."]
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


def test_list_refs_allow_at_most_3() -> None:
    reply = _good_reply()
    reply.reading = "I read this as {ref1} for [p1]."
    reply.list_refs = [
        ListRef(words="a", position=1, dimension=None),
        ListRef(words="b", position=2, dimension=None),
        ListRef(words="c", position=3, dimension=None),
    ]
    assert check_understanding(reply, _kb()) == []
    reply.list_refs.append(ListRef(words="d", position=4, dimension=None))
    assert check_understanding(reply, _kb()) != []


def test_a_period_shift_needs_a_non_zero_n() -> None:
    reply = _good_reply()
    reply.period_shift = PeriodShift(words="last year", unit="year", n=-1)
    assert check_understanding(reply, _kb()) == []
    reply.period_shift = PeriodShift(words="same time", unit="year", n=0)
    assert check_understanding(reply, _kb()) != []


def _kb_with_meanings() -> KbView:
    entries = {
        "metric": {"net_sales": {"kind": "sum"}, "gross_sales": {"kind": "sum"}},
        "dimension": {},
        "default": {
            "sales": {"word": "sales", "value": "net_sales", "metrics": ["net_sales"]},
            "best": {"word": "best", "value": "", "metrics": ["net_sales", "gross_sales"]},
        },
        "name": {},
    }
    return KbView(entries, {}, date(2025, 12, 31), {})


def test_a_with_default_reading_needs_a_settled_default() -> None:
    reply = _good_reply()
    reply.kind = "vague_with_default"
    reply.defaults_used = ["default.sales"]
    assert check_understanding(reply, _kb_with_meanings()) == []
    reply.defaults_used = ["default.best"]
    problems = check_understanding(reply, _kb_with_meanings())
    assert any("best" in problem for problem in problems)


def test_two_meanings_need_2_known_metrics() -> None:
    reply = _good_reply()
    reply.kind = "two_meanings"
    reply.meanings = [
        Meaning(label="Net sales", metric_key="net_sales"),
        Meaning(label="Gross sales", metric_key="gross_sales"),
    ]
    assert check_understanding(reply, _kb_with_meanings()) == []
    reply.meanings = reply.meanings[:1]
    assert check_understanding(reply, _kb_with_meanings()) != []
    reply.meanings = [
        Meaning(label="Net sales", metric_key="net_sales"),
        Meaning(label="Nope", metric_key="nope"),
    ]
    problems = check_understanding(reply, _kb_with_meanings())
    assert any("nope" in problem for problem in problems)


def test_about_refs_belong_to_about_answers() -> None:
    """Said refs name one earlier message and label, like 812:n1."""
    reply = _good_reply()
    reply.kind = "about_answer"
    reply.about = ["812:n1"]
    assert check_understanding(reply, _kb()) == []
    reply.about = ["n1"]
    problems = check_understanding(reply, _kb())
    assert any("812:n1" in problem for problem in problems)
    reply = _good_reply()
    reply.about = ["812:n1"]
    problems = check_understanding(reply, _kb())
    assert any("only for about_answer" in problem for problem in problems)


def test_missing_names_the_thing_without_digits() -> None:
    """not_in_data names the missing thing in a few words, no digits."""
    reply = _good_reply()
    reply.kind = "not_in_data"
    reply.missing = "market share"
    reply.document_topics = ["market share"]
    assert check_understanding(reply, _kb()) == []
    reply.missing = ""
    problems = check_understanding(reply, _kb())
    assert any("needs the missing thing" in problem for problem in problems)
    reply.missing = "market share 2025"
    problems = check_understanding(reply, _kb())
    assert any("must not type numbers" in problem for problem in problems)
    reply = _good_reply()
    reply.missing = "market share"
    problems = check_understanding(reply, _kb())
    assert any("only for not_in_data" in problem for problem in problems)


def test_a_ref_placeholder_needs_its_list_ref() -> None:
    reply = _good_reply()
    reply.reading = "I read this as {ref1} for [p1]."
    assert check_understanding(reply, _kb()) != []
    reply.list_refs = [ListRef(words="the second one", position=2, dimension=None)]
    assert check_understanding(reply, _kb()) == []


def _two_metric_kb() -> KbView:
    entries = {
        "metric": {"net_sales": {"kind": "sum"}, "delivered_amount": {"kind": "sum"}},
        "dimension": {},
        "default": {},
        "name": {},
        "calendar": {"cal": {"week_start": "monday", "fiscal_year_start": 1}},
    }
    texts = {
        "net_sales": {"title": "Net sales", "meaning": "Order totals minus tax and delivery fees."},
        "delivered_amount": {
            "title": "Delivered order amount",
            "meaning": "Order totals as charged.",
        },
        "cal": {"title": "Calendar", "meaning": "Business calendar."},
    }
    return KbView(entries, {}, date(2025, 12, 31), texts)


def _clear_reply_for(metric_key: str) -> Understanding:
    return Understanding(
        kind="clear",
        reading="I read this as net sales for [p1].",
        periods=[PeriodExpression(kind="month", number=12)],
        asks=[Ask(metric_key=metric_key)],
        filters=[],
        defaults_used=[],
        document_topics=[],
    )


def test_gross_key_for_net_sales_words_is_a_problem() -> None:
    reply = _clear_reply_for("delivered_amount")
    problems = check_understanding(
        reply, _two_metric_kb(), question="December orders and net sales"
    )
    assert any("Net sales" in problem for problem in problems)


def test_named_metric_key_is_fine() -> None:
    reply = _clear_reply_for("net_sales")
    assert (
        check_understanding(reply, _two_metric_kb(), question="December orders and net sales") == []
    )


def test_fit_check_skipped_without_question() -> None:
    reply = _clear_reply_for("delivered_amount")
    assert check_understanding(reply, _two_metric_kb()) == []


def test_fallback_drops_the_miskeyed_ask() -> None:
    from charie.chat.analyst.dates import DateContext

    kb = _two_metric_kb()
    reply = _clear_reply_for("delivered_amount")
    notes = apply_fallbacks(
        reply,
        kb,
        DateContext(today=date(2025, 12, 31), data_through=date(2025, 12, 31), data_from=None),
        ["Ask 1 uses the wrong metric."],
        question="December orders and net sales",
    )
    assert reply.asks == []
    assert any("Delivered order amount" in note and "Net sales" in note for note in notes)


def test_fallback_keeps_the_named_ask() -> None:
    from charie.chat.analyst.dates import DateContext

    kb = _two_metric_kb()
    reply = _clear_reply_for("net_sales")
    notes = apply_fallbacks(
        reply,
        kb,
        DateContext(today=date(2025, 12, 31), data_through=date(2025, 12, 31), data_from=None),
        [],
        question="December orders and net sales",
    )
    assert [ask.metric_key for ask in reply.asks] == ["net_sales"]
    assert notes == []


"""B020 exact case: gross recipe exists, net recipe does not."""


def _gross_only_kb() -> KbView:
    entries = {
        "metric": {"delivered_amount": {"kind": "sum"}},
        "dimension": {},
        "default": {},
        "name": {},
        "calendar": {"cal": {"week_start": "monday", "fiscal_year_start": 1}},
    }
    texts = {
        "delivered_amount": {
            "title": "Delivered order amount",
            "meaning": "Order totals as charged.",
        },
        "cal": {"title": "Calendar", "meaning": "Business calendar."},
    }
    return KbView(entries, {}, date(2025, 12, 31), texts)


def _kb_with_sales_default() -> KbView:
    entries = {
        "metric": {"net_sales": {"kind": "sum"}, "delivered_amount": {"kind": "sum"}},
        "dimension": {},
        "default": {"sales": {"word": "sales", "value": "net_sales"}},
        "name": {},
        "calendar": {"cal": {"week_start": "monday", "fiscal_year_start": 1}},
    }
    texts = {
        "net_sales": {"title": "Net sales", "meaning": "Order totals minus tax and delivery fees."},
        "delivered_amount": {
            "title": "Delivered order amount",
            "meaning": "Order totals as charged.",
        },
        "sales": {"title": "Sales", "meaning": "Completed orders."},
        "cal": {"title": "Calendar", "meaning": "Business calendar."},
    }
    return KbView(entries, {}, date(2025, 12, 31), texts)


def test_gross_key_for_unknown_net_term_is_unjustified() -> None:
    reply = _clear_reply_for("delivered_amount")
    problems = check_understanding(
        reply, _gross_only_kb(), question="December orders and net sales"
    )
    assert any("nothing in the question" in problem for problem in problems)


def test_gross_fallback_drops_without_guessing() -> None:
    from charie.chat.analyst.dates import DateContext

    kb = _gross_only_kb()
    reply = _clear_reply_for("delivered_amount")
    notes = apply_fallbacks(
        reply,
        kb,
        DateContext(today=date(2025, 12, 31), data_through=date(2025, 12, 31), data_from=None),
        ["Ask 1 uses the wrong metric."],
        question="December orders and net sales",
    )
    assert reply.asks == []
    assert any("did not guess" in note for note in notes)


def test_new_words_for_unknown_term_are_allowed() -> None:
    reply = Understanding(
        kind="clear",
        reading="I read this as net sales for [p1].",
        periods=[PeriodExpression(kind="month", number=12)],
        asks=[Ask(new_metric="net sales")],
        filters=[],
        defaults_used=[],
        document_topics=[],
    )
    kb = _gross_only_kb()
    assert check_understanding(reply, kb, question="December orders and net sales") == []
    from charie.chat.analyst.dates import DateContext

    notes = apply_fallbacks(
        reply,
        kb,
        DateContext(today=date(2025, 12, 31), data_through=date(2025, 12, 31), data_from=None),
        [],
        question="December orders and net sales",
    )
    assert [ask.new_metric for ask in reply.asks] == ["net sales"]
    assert notes == []


def test_used_default_justifies_its_metric() -> None:
    kb = _kb_with_sales_default()
    reply = _clear_reply_for("net_sales")
    reply.defaults_used = ["default.sales"]
    assert understand_module._default_targets(reply, kb) == {"net_sales"}
    assert check_understanding(reply, kb, question="How are we doing this month?") == []


def test_reading_alone_does_not_justify_gross() -> None:
    """Exact B020 case: the AI reading names gross; the user asked net sales."""
    reply = Understanding(
        kind="clear",
        reading="I read this as delivered order amount for [p1].",
        periods=[PeriodExpression(kind="month", number=12)],
        asks=[Ask(metric_key="delivered_amount")],
        filters=[],
        defaults_used=[],
        document_topics=[],
    )
    question = "What were net sales in December?"
    assert understand_module.unjustified_asks(reply, _gross_only_kb(), question) == {1: None}
    problems = check_understanding(reply, _gross_only_kb(), question=question)
    assert any("nothing in the question" in problem for problem in problems)


def test_inherited_follow_up_skips_the_fit_check() -> None:
    reply = Understanding(
        kind="follow_up",
        reading="I read this as delivered order amount.",
        periods=[],
        asks=[Ask(metric_key="delivered_amount")],
        filters=[],
        defaults_used=[],
        document_topics=[],
        inherit=["asks"],
        refs=[],
    )
    assert check_understanding(reply, _gross_only_kb(), question="Same for last year?") == []


def test_dropped_gross_starts_no_recipe_task() -> None:
    """Exact B020 case end to end: dropped gross never becomes a recipe task."""
    from charie.chat.analyst.dates import DateContext

    kb = _gross_only_kb()
    reply = _clear_reply_for("delivered_amount")
    apply_fallbacks(
        reply,
        kb,
        DateContext(today=date(2025, 12, 31), data_through=date(2025, 12, 31), data_from=None),
        ["Ask 1 uses the wrong metric."],
        question="December orders and net sales",
    )
    assert reply.asks == []
    tasks, _dropped = starter_tasks(reply, kb, "December orders and net sales")
    assert tasks == []
    assert all(task.kind != "recipe" for task in tasks)


"""B020: short default values resolve to kind-prefixed metric keys."""


def _prefixed_kb() -> KbView:
    entries = {
        "metric": {"metric.net_sales": {"kind": "sum"}},
        "dimension": {},
        "default": {"default.sales": {"word": "sales", "value": "net_sales"}},
        "name": {},
        "calendar": {"cal": {"week_start": "monday", "fiscal_year_start": 1}},
    }
    texts = {
        "metric.net_sales": {
            "title": "Net sales",
            "meaning": "Order totals minus tax and delivery fees.",
        },
        "default.sales": {"title": "sales", "meaning": "net_sales"},
        "cal": {"title": "Calendar", "meaning": "Business calendar."},
    }
    return KbView(entries, {}, date(2025, 12, 31), texts)


def test_prefixed_default_value_justifies_its_metric() -> None:
    """A used default justifies its metric even with kind-prefixed keys."""
    reply = Understanding(
        kind="vague_with_default",
        reading="I read this as sales without delivery fees for [p1].",
        periods=[PeriodExpression(kind="month", number=12)],
        asks=[Ask(metric_key="metric.net_sales")],
        filters=[],
        defaults_used=["default.sales"],
        document_topics=[],
    )
    assert (
        check_understanding(reply, _prefixed_kb(), question="What were sales in December 2025?")
        == []
    )
