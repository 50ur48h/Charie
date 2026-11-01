"""Follow-up references, worked out by code (P11.2)."""

from datetime import date

from charie.chat.analyst.chat_context import ChatContext, Focus, ShownList
from charie.chat.analyst.references import (
    ListRef,
    PeriodShift,
    Resolved,
    Unresolved,
    resolve_references,
    shift_period,
)
from charie.chat.analyst.understand import Ask, Filter, Understanding


def _ask(**overrides) -> dict:
    base = {"metric_key": "net_sales", "new_metric": "", "split_by": [], "top_n": None}
    base.update(overrides)
    return base


def _december(label: str = "p1") -> dict:
    return {
        "label": label,
        "expression": {"kind": "month", "number": 12, "year": 2025},
        "start": "2025-12-01",
        "end": "2025-12-31",
        "text": "1–31 Dec 2025",
    }


def _focus(asks=None, filters=None, periods=None) -> Focus:
    return Focus(
        message_id=7,
        question="Net sales?",
        kind="clear",
        asks=[_ask()] if asks is None else asks,
        filters=[] if filters is None else filters,
        periods=[_december()] if periods is None else periods,
    )


_UNSET = object()


def _shown(
    title: str = "Sales change by restaurant",
    dimension=_UNSET,
    items=("Downtown Austin", "Rice, Miller and Gutmann", "Third Place"),
) -> ShownList:
    return ShownList(
        message_id=7,
        title=title,
        dimension="restaurant" if dimension is _UNSET else dimension,
        items=list(items),
    )


def _context(focus=_UNSET, lists=()) -> ChatContext:
    return ChatContext(focus=_focus() if focus is _UNSET else focus, lists=list(lists))


def _u(**overrides) -> Understanding:
    base = {
        "kind": "follow_up",
        "reading": "I read this as net sales for [p1].",
        "periods": [],
        "asks": [],
        "filters": [],
        "defaults_used": [],
        "document_topics": [],
        "inherit": [],
        "list_refs": [],
        "period_shift": None,
    }
    base.update(overrides)
    return Understanding(**base)


def _ref(**overrides) -> ListRef:
    base = {"words": "the second one", "position": 2, "dimension": "restaurant"}
    base.update(overrides)
    return ListRef(**base)


def test_second_one_picks_item_two_of_newest_list() -> None:
    u = _u(
        reading="I read this as **net sales** for {ref1} for [p1].",
        list_refs=[_ref()],
    )
    result = resolve_references(u, _context(lists=[_shown()]))
    assert isinstance(result, Resolved)
    assert u.filters == [Filter(dimension_key="restaurant", values=["Rice, Miller and Gutmann"])]
    assert u.reading == "I read this as **net sales** for **Rice, Miller and Gutmann** for [p1]."
    assert result.lines == [
        '"the second one" is Rice, Miller and Gutmann, number 2 in "Sales change by restaurant".'
    ]


def test_last_one_picks_the_last_item() -> None:
    u = _u(list_refs=[_ref(words="the last one", position=-1)])
    result = resolve_references(u, _context(lists=[_shown()]))
    assert isinstance(result, Resolved)
    assert u.filters == [Filter(dimension_key="restaurant", values=["Third Place"])]
    assert result.lines == [
        '"the last one" is Third Place, number 3 in "Sales change by restaurant".'
    ]


def test_ref_with_dimension_skips_newer_lists_of_other_things() -> None:
    old = _shown(title="Sales by restaurant")
    new = _shown(title="Sales by cuisine", dimension="cuisine", items=("Italian", "Mexican"))
    u = _u(list_refs=[_ref()])
    result = resolve_references(u, _context(lists=[old, new]))
    assert isinstance(result, Resolved)
    assert u.filters == [Filter(dimension_key="restaurant", values=["Rice, Miller and Gutmann"])]


def test_ref_without_dimension_uses_the_newest_list() -> None:
    old = _shown(title="Sales by restaurant")
    new = _shown(title="Sales by cuisine", dimension="cuisine", items=("Italian", "Mexican"))
    u = _u(list_refs=[_ref(dimension=None)])
    result = resolve_references(u, _context(lists=[old, new]))
    assert isinstance(result, Resolved)
    assert u.filters == [Filter(dimension_key="cuisine", values=["Mexican"])]


def test_position_past_the_end_is_unresolved() -> None:
    u = _u(list_refs=[_ref(position=9)])
    result = resolve_references(u, _context(lists=[_shown()]))
    assert isinstance(result, Unresolved)
    assert result.words == "the second one"


def test_position_zero_is_unresolved() -> None:
    u = _u(list_refs=[_ref(position=0)])
    result = resolve_references(u, _context(lists=[_shown()]))
    assert isinstance(result, Unresolved)


def test_no_lists_is_unresolved() -> None:
    u = _u(list_refs=[_ref()])
    result = resolve_references(u, _context())
    assert isinstance(result, Unresolved)
    assert result.words == "the second one"


def test_neither_list_nor_ref_has_a_dimension_is_unresolved() -> None:
    u = _u(list_refs=[_ref(dimension=None)])
    result = resolve_references(u, _context(lists=[_shown(dimension=None)]))
    assert isinstance(result, Unresolved)


def test_inherit_keeps_asks_and_periods() -> None:
    u = _u(
        filters=[Filter(dimension_key="cuisine", values=["Italian"])],
        inherit=["asks", "periods"],
    )
    result = resolve_references(u, _context())
    assert isinstance(result, Resolved)
    assert u.asks == [Ask(**_ask())]
    assert [period.kind for period in u.periods] == ["month"]
    assert u.filters == [Filter(dimension_key="cuisine", values=["Italian"])]


def test_code_filter_replaces_question_filter_on_same_dimension() -> None:
    u = _u(
        filters=[Filter(dimension_key="restaurant", values=["Austin"])],
        list_refs=[_ref()],
    )
    result = resolve_references(u, _context(lists=[_shown()]))
    assert isinstance(result, Resolved)
    assert u.filters == [Filter(dimension_key="restaurant", values=["Rice, Miller and Gutmann"])]


def test_inherited_filters_leave_other_dimensions_alone() -> None:
    focus = _focus(filters=[{"dimension_key": "restaurant", "values": ["Dallas"]}])
    u = _u(
        filters=[Filter(dimension_key="cuisine", values=["Italian"])],
        inherit=["filters"],
    )
    result = resolve_references(u, _context(focus=focus))
    assert isinstance(result, Resolved)
    assert u.filters == [
        Filter(dimension_key="cuisine", values=["Italian"]),
        Filter(dimension_key="restaurant", values=["Dallas"]),
    ]


def test_three_months_before_december_is_september() -> None:
    u = _u(period_shift=PeriodShift(words="3 months before that", unit="month", n=-3))
    result = resolve_references(u, _context())
    assert isinstance(result, Resolved)
    assert [(period.start, period.end) for period in u.periods] == [
        (date(2025, 9, 1), date(2025, 9, 30))
    ]
    assert result.lines == ['"3 months before that" is 1–30 Sep 2025.']


def test_last_year_moves_the_comparison_too() -> None:
    periods = [
        _december("p1"),
        {
            "label": "p2",
            "expression": {"kind": "month", "number": 12, "year": 2024},
            "start": "2024-12-01",
            "end": "2024-12-31",
            "text": "1–31 Dec 2024",
        },
    ]
    u = _u(period_shift=PeriodShift(words="last year", unit="year", n=-1))
    result = resolve_references(u, _context(focus=_focus(asks=[], periods=periods)))
    assert isinstance(result, Resolved)
    assert [(period.start, period.end) for period in u.periods] == [
        (date(2024, 12, 1), date(2024, 12, 31)),
        (date(2023, 12, 1), date(2023, 12, 31)),
    ]


def test_march_minus_one_month_is_february() -> None:
    day = date(2025, 3, 31)
    assert shift_period(day, day, "month", -1) == (date(2025, 2, 28), date(2025, 2, 28))


def test_week_and_day_shifts_move_every_date() -> None:
    start, end = date(2025, 12, 8), date(2025, 12, 14)
    assert shift_period(start, end, "week", -1) == (date(2025, 12, 1), date(2025, 12, 7))
    assert shift_period(start, end, "day", 3) == (date(2025, 12, 11), date(2025, 12, 17))


def test_quarter_shift_keeps_the_whole_quarter() -> None:
    start, end = date(2025, 10, 1), date(2025, 12, 31)
    assert shift_period(start, end, "quarter", -1) == (date(2025, 7, 1), date(2025, 9, 30))


def test_each_ref_placeholder_becomes_its_bold_item_name() -> None:
    u = _u(
        reading="I read this as {ref1} against {ref2} for [p1].",
        list_refs=[_ref(words="the second one"), _ref(words="the last one", position=-1)],
    )
    result = resolve_references(u, _context(lists=[_shown()]))
    assert isinstance(result, Resolved)
    assert u.reading == (
        "I read this as **Rice, Miller and Gutmann** against **Third Place** for [p1]."
    )


def test_kept_from_before_names_taken_parts() -> None:
    focus = _focus(filters=[{"dimension_key": "restaurant", "values": ["Dallas"]}])
    u = _u(inherit=["asks", "filters", "periods"])
    result = resolve_references(u, _context(focus=focus))
    assert isinstance(result, Resolved)
    assert result.lines == ["Kept from before: net sales; Dallas; 1–31 Dec 2025."]


def test_shift_without_periods_in_focus_is_unresolved() -> None:
    u = _u(period_shift=PeriodShift(words="same for last year", unit="year", n=-1))
    result = resolve_references(u, _context(focus=_focus(periods=[])))
    assert isinstance(result, Unresolved)
    assert result.words == "same for last year"


def test_empty_focus_resolves_with_no_lines() -> None:
    u = _u(inherit=["asks", "filters", "periods"])
    result = resolve_references(u, _context(focus=None))
    assert isinstance(result, Resolved)
    assert u.asks == [] and u.filters == [] and u.periods == []
    assert result.lines == []
