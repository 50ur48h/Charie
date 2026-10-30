"""Value shapes and the 80% rule (P07.7)."""

from charie.learner.patterns import main_pattern, shape


def test_shape_of_codes() -> None:
    assert shape("MEGA0926") == "AAAA9999"
    assert shape("save-10%") == "AAAA-99%"
    assert shape("") == ""


def test_main_pattern_needs_80_percent() -> None:
    assert main_pattern(["SAVE10"] * 4 + ["xx"]) == ("AAAA99", 0.8)
    pattern, share = main_pattern(["SAVE10"] * 3 + ["xx", "y"])
    assert pattern is None and share == 0.6


def test_no_values_gives_no_pattern() -> None:
    assert main_pattern([]) == (None, 0.0)
