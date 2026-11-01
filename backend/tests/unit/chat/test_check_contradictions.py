"""No contradictions within a chat (P11.4)."""

from charie.chat.analyst.checks import (
    ChangedNumber,
    CheckInputs,
    correction_note_text,
    find_changed_numbers,
    run_checks,
)
from charie.chat.analyst.notebook import NotebookItem, NumberValue
from charie.chat.analyst.write import AnswerDraft


def _fact():
    return {
        "metric": "net_sales",
        "filters": [],
        "split": {},
        "period": "a/b",
        "compare_period": "",
        "measure": "value",
    }


def _number(value="360.00", fact=None):
    return NotebookItem(
        label="n1",
        kind="number",
        description="Net sales",
        value=NumberValue(value=value, unit="money").model_dump(),
        proof={"fact_key": _fact() if fact is None else fact},
    )


def _said(raw="355.00", text="$355.00", data_through="2025-12-31", kb_version=1):
    return {
        "fact_key": _fact(),
        "raw": raw,
        "text": text,
        "description": "Net sales",
        "data_through": data_through,
        "kb_version": kb_version,
        "message_id": 7,
    }


def _draft():
    from charie.chat.analyst.write import DraftBlock, DraftSentence

    return AnswerDraft(
        blocks=[
            DraftBlock(
                type="text",
                sentences=[
                    DraftSentence(
                        kind="fact",
                        text="Sales were [n1].",
                        proof=["n1"],
                        starts_paragraph=True,
                    )
                ],
            )
        ]
    )


def test_same_value_is_not_a_changed_number() -> None:
    """Exact decimals match even when the formatting differs."""
    assert find_changed_numbers([_number("360")], [_said("360.00")], "2025-12-31", 1) == []


def test_different_value_with_later_data_is_data_updated() -> None:
    (changed,) = find_changed_numbers([_number("360.00")], [_said()], "2026-01-31", 1)
    assert changed.reason == "data_updated"
    assert changed.label == "n1"
    assert changed.old_text == "$355.00"
    assert changed.new_raw == "360.00"


def test_different_value_with_another_knowledge_version_is_knowledge_updated() -> None:
    (changed,) = find_changed_numbers([_number("360.00")], [_said()], "2025-12-31", 2)
    assert changed.reason == "knowledge_updated"


def test_different_value_with_nothing_changed_is_unknown() -> None:
    (changed,) = find_changed_numbers([_number("360.00")], [_said()], "2025-12-31", 1)
    assert changed.reason == "unknown"


def test_only_shown_numbers_are_compared() -> None:
    """A notebook number never shown in this chat can't contradict."""
    other = _fact()
    other["metric"] = "gross_sales"
    assert find_changed_numbers([_number("360.00", fact=other)], [_said()], "2025-12-31", 1) == []


def test_a_planted_contradiction_is_caught() -> None:
    """An unexplained changed number fails check 9 with the leave-it-out message."""
    draft = _draft()
    inputs = CheckInputs(
        items=[_number("360.00")],
        values={"n1": "$360.00"},
        data_through="2025-12-31",
        kb_version_id=1,
        earlier_numbers=[_said()],
    )
    (failure,) = run_checks(draft, [{"type": "text"}], inputs)
    assert failure.check == 9
    assert failure.message == (
        "Leave [n1] out of the answer: earlier in this chat I said $355.00 "
        "for the same number, place and period, and I can't explain why it changed."
    )


def test_a_noted_correction_passes() -> None:
    """A known change with a code-written correction note passes check 9."""
    changed = ChangedNumber(
        label="n1",
        description="Net sales",
        old_text="$355.00",
        new_raw="360.00",
        reason="data_updated",
    )
    note = correction_note_text(changed, "$360.00", "2026-01-31")
    assert note == (
        "Correction: earlier in this chat I said Net sales was $355.00. "
        "It's now $360.00, because more data has come in (it now goes up to 31 Jan 2026)."
    )
    inputs = CheckInputs(
        items=[_number("360.00")],
        values={"n1": "$360.00"},
        data_through="2026-01-31",
        kb_version_id=1,
        earlier_numbers=[_said()],
        corrected=["n1"],
    )
    assert run_checks(_draft(), [{"type": "text"}], inputs) == []
