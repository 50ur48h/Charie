"""Labels: finding, filling and stray digits (P10.4)."""

from charie.chat.analyst.labels import fill_labels, labels_in, mixed_tokens, stray_digits


def test_labels_in_finds_all_labels() -> None:
    assert labels_in("I read this as net sales for [p1], compared with [p2].") == ["p1", "p2"]
    assert labels_in("No labels here.") == []
    assert labels_in("[n1] and [n1] again") == ["n1", "n1"]


def test_fill_labels_replaces_known_labels() -> None:
    filled = fill_labels("Sales for [p1] vs [p2].", {"p1": "December 2025"})
    assert filled == "Sales for December 2025 vs [p2]."


def test_stray_digits_outside_labels() -> None:
    assert stray_digits("Sales for [p1].", []) == []
    assert stray_digits("Sales were 42 last month.", []) == ["42"]
    assert stray_digits("Up 6.2% on [p2].", []) == ["6.2%"]


def test_mixed_token_allowed_when_known() -> None:
    assert stray_digits("Use code MEGA0926.", ["MEGA0926"]) == []
    assert stray_digits("Use code MEGA0926.", []) == ["MEGA0926"]


def test_bare_numbers_never_allowed() -> None:
    assert stray_digits("42 orders.", ["42"]) == ["42"]
    assert mixed_tokens(["Use code MEGA0926 twice"]) == ["MEGA0926"]
    assert mixed_tokens(["plain words", "42"]) == []
