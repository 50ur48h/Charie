"""The definitions the eval organization is provisioned with (B-070)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from charie.semantic.definitions import Definition, RequiredFilter, matching

_EVALS = Path(__file__).resolve().parents[4] / "ops" / "evals"
if str(_EVALS) not in sys.path:
    sys.path.insert(0, str(_EVALS))

from provision import EVAL_DEFINITIONS  # noqa: E402

REPEAT_RATE = next(spec for spec in EVAL_DEFINITIONS if spec["name"] == "repeat_rate")


def _definitions() -> tuple[Definition, ...]:
    """The provisioned specs as the objects `matching` is given at run time."""
    import uuid

    return tuple(
        Definition(
            id=uuid.uuid4(),
            name=str(spec["name"]),
            kind="metric",
            description=str(spec["description"]),
            expression=str(spec["expression"]),
            required_filters=tuple[RequiredFilter](),
            synonyms=tuple(str(word) for word in spec["synonyms"]),  # type: ignore[union-attr]
        )
        for spec in EVAL_DEFINITIONS
    )


def _golden_question(case_id: int) -> str:
    cases = yaml.safe_load((_EVALS / "golden.yaml").read_text(encoding="utf-8"))
    return next(case["question"] for case in cases if case["id"] == case_id)


def test_golden_ten_reaches_the_definition_that_disambiguates_it() -> None:
    """The test that stops this rotting."""
    applied = matching(_definitions(), _golden_question(10))

    assert [definition.name for definition in applied] == ["repeat_rate"]


def test_the_definition_says_which_denominator_is_authoritative() -> None:
    """The whole content of the fix."""
    description = str(REPEAT_RATE["description"])

    assert "denominator" in description
    assert "not every customer on file" in description


def test_it_binds_nothing_and_does_not_pretend_to() -> None:
    """The ambiguity is in which rows are counted."""
    assert "required_filters" not in REPEAT_RATE


def test_it_is_not_attached_to_a_question_about_a_different_proportion() -> None:
    """The synonyms are narrow on purpose."""
    assert matching(_definitions(), "what proportion of customers are in the north region?") == ()


def test_a_question_about_orders_alone_is_left_alone() -> None:
    assert matching(_definitions(), "how many orders were placed last month?") == ()
