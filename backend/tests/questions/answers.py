"""Test answers: what an answer function returns for one question (06, 08)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from tests.questions.format import Question


@dataclass(frozen=True)
class ShownNumber:
    """One number the answer shows, with its label and unit."""

    label: str
    value: Decimal
    unit: str = ""
    description: str = ""


@dataclass(frozen=True)
class TestAnswer:
    """Everything the scorer needs: text, shown numbers, and what it cost."""

    text: str
    numbers: list[ShownNumber] = field(default_factory=list)
    asked_choice: bool = False
    status: str = "ok"
    error: str = ""
    seconds: float = 0.0
    cost_usd: Decimal = Decimal("0")
    earlier_turns_cost_usd: Decimal = Decimal("0")
    chat_url: str = ""


TestAnswer.__test__ = False  # A dataclass, not a pytest test class.


class AnswerFunction(Protocol):
    """Ask one question (after its `chat` lines); `private` hides the traces."""

    def __call__(self, question: Question, private: bool) -> TestAnswer: ...


def _first_choice(must_say: str) -> str:
    """The first of the `a | b` choices."""
    return must_say.split("|", 1)[0].strip()


def fake_answer(question: Question, overrides: Mapping[str, TestAnswer]) -> TestAnswer:
    """Copy the answer key: every expected number, the first `must_say` choice.

    `asked_choice` follows `should_ask`; it costs nothing. `overrides` replaces
    the copy for the ids it holds, one question per outcome in the tests.
    """
    if question.id in overrides:
        return overrides[question.id]
    numbers = [
        ShownNumber(label=expected.name, value=expected.value)
        for expected in question.expect.numbers
    ]
    shown = [f"{expected.name}: {expected.value}" for expected in question.expect.numbers]
    shown += [_first_choice(text) for text in question.expect.must_say]
    return TestAnswer(
        text="; ".join(shown), numbers=numbers, asked_choice=question.expect.should_ask
    )
