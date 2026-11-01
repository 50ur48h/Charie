"""Answer checks 1–5 and 10 on small made-up notebooks (P10.11)."""

from charie.chat.analyst.checks import CheckInputs, run_checks
from charie.chat.analyst.notebook import (
    NotebookItem,
    NumberValue,
    PeriodValue,
    TableColumn,
    TableValue,
)
from charie.chat.analyst.write import AnswerDraft, DraftBlock, DraftChart, DraftKpi, DraftSentence


def _number(label, value="359.00", unit="money", status="ok", replaced_by="", proof=None):
    return NotebookItem(
        label=label,
        kind="number",
        description="Net sales",
        value=NumberValue(value=value, unit=unit).model_dump(),
        status=status,
        replaced_by=replaced_by,
        proof=proof or {},
    )


def _period(label="p1"):
    return NotebookItem(
        label=label,
        kind="period",
        description="1–31 Dec 2025",
        value=PeriodValue(
            start="2025-12-01",
            end="2025-12-31",
            text="1–31 Dec 2025",
            partial=False,
            expression="month 2025-12",
        ).model_dump(),
    )


def _table(label="t1", rows=None, total=None, timed=False):
    columns = [
        TableColumn(key="month" if timed else "restaurant", label="Month", is_time=timed),
        TableColumn(key="sales", label="Sales", unit="money", currency="USD"),
    ]
    rows = rows if rows is not None else [["2025-11-01", "100"], ["2025-12-01", "120"]]
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


def _sentence(text, kind="fact", proof=None):
    return DraftSentence(
        kind=kind, text=text, proof=proof if proof is not None else [], starts_paragraph=True
    )


def _draft(*sentences):
    return AnswerDraft(blocks=[DraftBlock(type="text", sentences=list(sentences))])


def _inputs(*items, kind="clear", allowed=None):
    return CheckInputs(items=list(items), kind=kind, allowed_tokens=allowed or [])


def test_good_draft_passes() -> None:
    """Labels that resolve and words from the notebook pass every check."""
    draft = _draft(_sentence("Net sales were [n1] in [p1].", proof=["n1"]))
    assert run_checks(draft, [], _inputs(_number("n1"), _period())) == []


def test_typed_digit_fails() -> None:
    """A fresh figure the writer typed fails check 1."""
    draft = _draft(_sentence("Net sales were 1.4M [n1].", kind="note"))
    (failure,) = run_checks(draft, [], _inputs(_number("n1")))
    assert (failure.check, failure.where) == (1, "Block 1, sentence 1")
    assert failure.message == (
        'Block 1, sentence 1: "1.4M" is a number the writer typed. Use a label like [n1] instead.'
    )


def test_digit_in_chart_title_fails() -> None:
    """Years in a chart title fail the same check."""
    draft = AnswerDraft(
        blocks=[
            DraftBlock(
                type="chart",
                chart=DraftChart(kind="bar", title="Sales 2025", table="t1", x="a", y="b"),
            )
        ]
    )
    (failure,) = run_checks(draft, [], _inputs(_table()))
    assert failure.check == 1
    assert failure.message == (
        'Block 1: "2025" is a number the writer typed. Use a label like [n1] instead.'
    )


def test_bare_year_fails() -> None:
    """A year the notebook only shows inside a period still fails."""
    draft = _draft(_sentence("In 2025 sales held.", kind="note"))
    (failure,) = run_checks(draft, [], _inputs(_period()))
    assert failure.check == 1
    assert '"2025" is a number the writer typed.' in failure.message


def test_known_code_with_digits_allowed() -> None:
    """A coupon code from the notebook may keep its digits."""
    draft = _draft(_sentence("Coupon MEGA0926 worked [n1].", kind="note", proof=["n1"]))
    assert run_checks(draft, [], _inputs(_number("n1"), allowed=["MEGA0926"])) == []


def test_unknown_code_with_digits_fails() -> None:
    """A code nobody taught Charie fails like any typed number."""
    draft = _draft(_sentence("Coupon ABC123 worked.", kind="note"))
    (failure,) = run_checks(draft, [], _inputs())
    assert failure.check == 1
    assert '"ABC123" is a number the writer typed.' in failure.message


def test_unknown_label_fails() -> None:
    """A label from nowhere fails check 2."""
    draft = _draft(_sentence("[n9] is big.", proof=["n9"]))
    (failure,) = run_checks(draft, [], _inputs(_number("n1")))
    assert (failure.check, failure.where) == (2, "Block 1, sentence 1")
    assert failure.message == ("Block 1, sentence 1: Label [n9] isn't in this question's notebook.")


def test_replaced_label_fails() -> None:
    """A replaced label names its replacement."""
    old = _number("n1", status="replaced", replaced_by="n2")
    draft = _draft(_sentence("[n1] is big.", proof=["n1"]))
    (failure,) = run_checks(draft, [], _inputs(old, _number("n2", "360.00")))
    assert failure.check == 2
    assert failure.message == ("Block 1, sentence 1: Label [n1] was replaced; use [n2] instead.")


def test_kpi_with_table_label_fails() -> None:
    """A number card needs a number label."""
    draft = AnswerDraft(
        blocks=[DraftBlock(type="kpis", kpis=[DraftKpi(title="Net sales", value="t1")])]
    )
    (failure,) = run_checks(draft, [], _inputs(_table()))
    assert failure.check == 2
    assert failure.message == ("Block 1: A number card needs a number label (n…), not [t1].")


def test_chart_with_number_label_fails() -> None:
    """A chart needs a table label."""
    draft = AnswerDraft(
        blocks=[
            DraftBlock(
                type="chart",
                chart=DraftChart(kind="bar", title="Sales", table="n1", x="a", y="b"),
            )
        ]
    )
    (failure,) = run_checks(draft, [], _inputs(_number("n1")))
    assert failure.check == 2
    assert failure.message == ("Block 1: A chart or table needs a table label (t…), not [n1].")


def test_fact_without_proof_fails() -> None:
    """A fact with no proof fails check 3."""
    draft = _draft(_sentence("Net sales were [n1].", proof=[]))
    (failure,) = run_checks(draft, [], _inputs(_number("n1")))
    assert failure.check == 3
    assert failure.message == (
        "Block 1, sentence 1: This fact has no proof. "
        "Add at least one n, t or q label to its proof."
    )


def test_conclusion_with_only_period_proof_fails() -> None:
    """A period alone proves nothing."""
    draft = _draft(_sentence("December was good [p1].", kind="conclusion", proof=["p1"]))
    (failure,) = run_checks(draft, [], _inputs(_number("n1"), _period()))
    assert failure.check == 3
    assert "This conclusion has no proof." in failure.message


def test_possible_reason_without_careful_word_fails() -> None:
    """A certain-sounding reason fails check 4."""
    draft = _draft(_sentence("The menu changed [n1].", kind="possible_reason", proof=["n1"]))
    (failure,) = run_checks(draft, [], _inputs(_number("n1")))
    assert failure.check == 4
    assert failure.message == (
        "Block 1, sentence 1: A possible reason must sound possible. "
        'Use "may", "might", "possibly", "a likely reason" or "could".'
    )


def test_possible_reason_with_a_likely_reason_passes() -> None:
    """'A likely reason' sounds possible."""
    draft = _draft(
        _sentence("A likely reason is the holiday menu [n1].", kind="possible_reason", proof=["n1"])
    )
    assert run_checks(draft, [], _inputs(_number("n1"))) == []


def test_trend_without_time_series_fails() -> None:
    """'Rising' with a plain split table fails check 5."""
    table = _table(rows=[["Downtown", "10"], ["Uptown", "12"]])
    draft = _draft(_sentence("Sales are rising [t1].", kind="conclusion", proof=["t1"]))
    (failure,) = run_checks(draft, [], _inputs(table))
    assert failure.check == 5
    assert failure.message == ('Block 1, sentence 1: "rising" needs a time-series table as proof.')


def test_fake_trend_fails() -> None:
    """'Rising' when the series falls names the real direction and steps."""
    table = _table(
        rows=[
            ["2025-09-01", "10"],
            ["2025-10-01", "12"],
            ["2025-11-01", "13"],
            ["2025-12-01", "9"],
        ],
        timed=True,
    )
    draft = _draft(_sentence("Sales are rising [t1].", kind="conclusion", proof=["t1"]))
    (failure,) = run_checks(draft, [], _inputs(table))
    assert failure.check == 5
    assert failure.message == (
        'Block 1, sentence 1: "rising" doesn\'t match the data in [t1]: '
        "it goes down overall, with 1 of 3 steps going that way."
    )


def test_two_point_trend_fails() -> None:
    """Two points are never a time series."""
    table = _table(rows=[["2025-11-01", "10"], ["2025-12-01", "12"]], total=2, timed=True)
    draft = _draft(_sentence("Sales are rising [t1].", kind="conclusion", proof=["t1"]))
    (failure,) = run_checks(draft, [], _inputs(table))
    assert failure.check == 5
    assert "needs a time-series table as proof" in failure.message


def test_real_trend_passes() -> None:
    """A real climb with proof passes every check."""
    table = _table(
        rows=[
            ["2025-09-01", "10"],
            ["2025-10-01", "12"],
            ["2025-11-01", "11"],
            ["2025-12-01", "15"],
        ],
        timed=True,
    )
    draft = _draft(_sentence("Sales are rising [t1].", kind="conclusion", proof=["t1"]))
    assert run_checks(draft, [], _inputs(table)) == []


def test_vague_without_reading_fails() -> None:
    """A vague question must start with the reading block."""
    draft = _draft(_sentence("Net sales were [n1].", proof=["n1"]))
    (failure,) = run_checks(
        draft, [{"type": "text"}], _inputs(_number("n1"), kind="vague_with_default")
    )
    assert failure.check == 10
    assert failure.message == (
        'Block 1: The question was vague, so the answer must start with "I read this as…".'
    )


def test_messages_are_plain_english() -> None:
    """Every failure message, word for word."""
    table = _table(rows=[["2025-11-01", "10"], ["2025-12-01", "12"]], total=2, timed=True)
    old = _number("n1", status="replaced", replaced_by="n2")
    draft = AnswerDraft(
        blocks=[
            DraftBlock(
                type="text",
                sentences=[
                    _sentence("Net sales were 1.4M [n2].", kind="note"),
                    _sentence("[n9] is big.", proof=["n9"]),
                    _sentence("[n1] is big.", proof=["n1"]),
                    _sentence("The menu changed.", kind="possible_reason"),
                    _sentence("Sales are rising [t1].", kind="conclusion", proof=["t1"]),
                ],
            )
        ]
    )
    messages = [
        failure.message
        for failure in run_checks(draft, [], _inputs(old, _number("n2", "360.00"), table))
    ]
    assert messages == [
        'Block 1, sentence 1: "1.4M" is a number the writer typed. Use a label like [n1] instead.',
        "Block 1, sentence 2: Label [n9] isn't in this question's notebook.",
        "Block 1, sentence 3: Label [n1] was replaced; use [n2] instead.",
        "Block 1, sentence 4: A possible reason must sound possible. "
        'Use "may", "might", "possibly", "a likely reason" or "could".',
        'Block 1, sentence 5: "rising" needs a time-series table as proof.',
    ]
