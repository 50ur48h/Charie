"""Answer checks 6–10 on small made-up notebooks (P10.12)."""

from charie.chat.analyst.checks import CheckInputs, run_checks
from charie.chat.analyst.notebook import (
    NotebookItem,
    NumberValue,
    QuoteValue,
    TableColumn,
    TableValue,
)
from charie.chat.analyst.write import AnswerDraft, DraftBlock, DraftChart, DraftSentence


def _number(label, value="359.00", unit="money", proof=None):
    return NotebookItem(
        label=label,
        kind="number",
        description="Net sales",
        value=NumberValue(value=value, unit=unit).model_dump(),
        proof=proof or {},
    )


def _table(label="t1", rows=None, total=None, timed=False, unit="money"):
    columns = [
        TableColumn(key="month" if timed else "restaurant", label="Month", is_time=timed),
        TableColumn(key="sales", label="Sales", unit=unit, currency="USD"),
    ]
    rows = rows if rows is not None else [["Downtown", "10"], ["Uptown", "12"]]
    return NotebookItem(
        label=label,
        kind="table",
        description="Sales",
        value=TableValue(
            columns=columns,
            rows=rows,
            rows_total=total if total is not None else len(rows),
            sql="SELECT 1",
        ).model_dump(),
    )


def _quote(label="q1", text="fresh daily", section="fresh daily bread", document="notes"):
    return NotebookItem(
        label=label,
        kind="quote",
        description="Freshness note",
        value=QuoteValue(
            text=text,
            document_id=1,
            document=document,
            section_id=4,
            heading_path="",
            location="page 1",
        ).model_dump(),
    )


def _sentence(text, kind="fact", proof=None):
    return DraftSentence(
        kind=kind, text=text, proof=proof if proof is not None else [], starts_paragraph=True
    )


def _draft(*sentences):
    return AnswerDraft(blocks=[DraftBlock(type="text", sentences=list(sentences))])


def _chart_block(title="Sales", table="t1", x="restaurant", y="sales", rows=None, unit="money"):
    rows = (
        rows
        if rows is not None
        else [["Uptown", {"v": 12.0, "f": "$12.00"}], ["Downtown", {"v": 10.0, "f": "$10.00"}]]
    )
    return {
        "type": "chart",
        "kind": "bar",
        "title": title,
        "subtitle": "",
        "x": x,
        "y": y,
        "unit": unit,
        "currency": "USD",
        "highlight": [],
        "data": {"columns": [x, y], "rows": rows},
    }


def _chart_draft(table="t1", x="restaurant", y="sales", highlight=None, title="Sales"):
    return AnswerDraft(
        blocks=[
            DraftBlock(
                type="chart",
                chart=DraftChart(
                    kind="bar",
                    title=title,
                    table=table,
                    x=x,
                    y=y,
                    highlight=highlight or [],
                ),
            )
        ]
    )


def test_chart_with_missing_table_fails() -> None:
    """A chart of a table that isn't there fails check 6."""
    failures = run_checks(_chart_draft(table="t9"), [_chart_block()], CheckInputs())
    assert "Block 1: The chart's table [t9] isn't in the notebook." in [
        failure.message for failure in failures if failure.check == 6
    ]


def test_sorted_bars_pass() -> None:
    """Bars largest first pass check 6."""
    assert run_checks(_chart_draft(), [_chart_block()], CheckInputs(items=[_table()])) == []


def test_unsorted_bars_fail() -> None:
    """Bars must run largest first."""
    rows = [["Downtown", {"v": 10.0, "f": "$10.00"}], ["Uptown", {"v": 12.0, "f": "$12.00"}]]
    (failure,) = run_checks(
        _chart_draft(), [_chart_block(rows=rows)], CheckInputs(items=[_table()])
    )
    assert failure.check == 6
    assert failure.message == "Block 1: Bars must be sorted by value."


def test_time_out_of_order_fails() -> None:
    """Time runs left to right, oldest first."""
    table = _table(timed=True)
    rows = [
        ["2025-12-01", {"v": 120.0, "f": "$120.00"}],
        ["2025-11-01", {"v": 100.0, "f": "$100.00"}],
    ]
    (failure,) = run_checks(
        _chart_draft(x="month"), [_chart_block(x="month", rows=rows)], CheckInputs(items=[table])
    )
    assert failure.check == 6
    assert failure.message == "Block 1: Time must run left to right, oldest first."


def test_mixed_units_fails() -> None:
    """The axis unit must match its column."""
    (failure,) = run_checks(
        _chart_draft(), [_chart_block(unit="count")], CheckInputs(items=[_table()])
    )
    assert failure.check == 6
    assert failure.message == "Block 1: One axis mixes units or currencies."


def test_missing_highlight_fails() -> None:
    """A highlighted name must be in the data."""
    (failure,) = run_checks(
        _chart_draft(highlight=["Nowhere"]),
        [_chart_block()],
        CheckInputs(items=[_table()]),
    )
    assert failure.check == 6
    assert failure.message == 'Block 1: "Nowhere" is highlighted but isn\'t in the data.'


def test_too_many_bars_fails() -> None:
    """A chart can show at most 30 bars."""
    rows = [[f"r{number}", {"v": float(number), "f": str(number)}] for number in range(31, 0, -1)]
    (failure,) = run_checks(
        _chart_draft(), [_chart_block(rows=rows)], CheckInputs(items=[_table()])
    )
    assert failure.check == 6
    assert failure.message == "Block 1: A chart can show at most 30 bars."


def test_required_note_missing_fails() -> None:
    """A used table's required note must appear."""
    draft = _draft(_sentence("Net sales were [n1].", proof=["n1"]))
    inputs = CheckInputs(
        items=[_number("n1")],
        question="How are we doing?",
        query_runs=[{"check_report": {"tables": ["shop.orders"]}}],
        required_notes=[
            {
                "note_text": "Outlet profit is illustrative, not audited",
                "applies_to_tables": ["shop.orders"],
                "applies_to_words": [],
            }
        ],
    )
    (failure,) = run_checks(draft, [{"type": "text"}], inputs)
    assert failure.check == 7
    assert failure.message == (
        "This answer uses shop.orders, so it must include the note "
        '"Outlet profit is illustrative, not audited".'
    )


def test_required_note_by_word() -> None:
    """A word in the question can require the note."""
    draft = _draft(_sentence("Net sales were [n1].", proof=["n1"]))
    inputs = CheckInputs(
        items=[_number("n1")],
        question="Tell me about outlet profit.",
        required_notes=[
            {
                "note_text": "Outlet profit is illustrative, not audited",
                "applies_to_tables": [],
                "applies_to_words": ["outlet profit"],
            }
        ],
    )
    (failure,) = run_checks(draft, [{"type": "text"}], inputs)
    assert failure.check == 7
    assert "must include the note" in failure.message


def test_altered_quote_fails() -> None:
    """A quote that no longer appears word for word fails check 8."""
    draft = _draft(_sentence("She said [q1] today.", proof=["q1"]))
    inputs = CheckInputs(
        items=[_quote()],
        section_texts=[{"label": "q1", "text": "stale daily bread", "document": "notes"}],
    )
    (failure,) = run_checks(draft, [], inputs)
    assert failure.check == 8
    assert failure.message == "Quote [q1] doesn't appear word for word in notes."


def test_unchecked_quote_fails() -> None:
    """A long quoted passage must be a checked quote."""
    draft = _draft(_sentence('She said "fresh daily bread today".', kind="note"))
    inputs = CheckInputs(items=[_quote()])
    (failure,) = run_checks(draft, [], inputs)
    assert failure.check == 8
    assert failure.message == (
        'Block 1, sentence 1: "fresh daily bread today" isn\'t a checked quote. '
        "Use a quote label like [q1]."
    )


def test_short_quote_passes() -> None:
    """Three quoted words are just emphasis."""
    draft = _draft(_sentence('She said "very fresh bread".', kind="note"))
    assert run_checks(draft, [], CheckInputs(items=[_quote()])) == []


def test_contradiction_without_reason_fails() -> None:
    """An unexplained changed number fails check 9."""
    fact = {
        "metric": "net_sales",
        "filters": [],
        "split": {},
        "period": "a/b",
        "compare_period": "",
        "measure": "value",
    }
    draft = _draft(_sentence("Sales were [n1].", proof=["n1"]))
    inputs = CheckInputs(
        items=[_number("n1", "360.00", proof={"fact_key": fact})],
        values={"n1": "$360.00"},
        data_through="2025-12-31T00:00:00+00:00",
        kb_version_id=1,
        earlier_numbers=[
            {
                "fact_key": fact,
                "raw": "355.00",
                "text": "$355.00",
                "description": "Net sales",
                "data_through": "2025-12-31T00:00:00+00:00",
                "kb_version": 1,
                "message_id": 7,
            }
        ],
    )
    (failure,) = run_checks(draft, [], inputs)
    assert failure.check == 9
    assert failure.message == (
        "Leave [n1] out of the answer: earlier in this chat I said $355.00 "
        "for the same number, place and period, and I can't explain why it changed."
    )


def test_explained_change_passes() -> None:
    """New data plus a citing note sentence explains the change."""
    fact = {
        "metric": "net_sales",
        "filters": [],
        "split": {},
        "period": "a/b",
        "compare_period": "",
        "measure": "value",
    }
    draft = AnswerDraft(
        blocks=[
            DraftBlock(
                type="text",
                sentences=[
                    _sentence("Sales were [n1].", proof=["n1"]),
                    DraftSentence(
                        kind="note",
                        text="New data: [n1] runs to January.",
                        proof=["n1"],
                        starts_paragraph=True,
                    ),
                ],
            )
        ]
    )
    inputs = CheckInputs(
        items=[_number("n1", "360.00", proof={"fact_key": fact})],
        values={"n1": "$360.00"},
        data_through="2026-01-31T00:00:00+00:00",
        kb_version_id=1,
        earlier_numbers=[
            {
                "fact_key": fact,
                "raw": "355.00",
                "text": "$355.00",
                "description": "Net sales",
                "data_through": "2025-12-31T00:00:00+00:00",
                "kb_version": 1,
                "message_id": 7,
            }
        ],
    )
    assert run_checks(draft, [], inputs) == []
