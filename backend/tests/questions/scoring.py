"""Scores: code checks the numbers, the judge scores the explanation (08)."""

from dataclasses import dataclass, field
from decimal import Decimal

from tests.questions.answers import TestAnswer
from tests.questions.format import Question
from tests.questions.judge import JudgeVerdict, judge_score

CORRECT = Decimal(1)
PARTLY = Decimal("0.5")
ZERO = Decimal(0)
WRONG = Decimal(-1)

PASS_SCORE = 0.7

_MONTHS = {
    "january": "jan",
    "february": "feb",
    "march": "mar",
    "april": "apr",
    "may": "may",
    "june": "jun",
    "july": "jul",
    "august": "aug",
    "september": "sep",
    "october": "oct",
    "november": "nov",
    "december": "dec",
}


@dataclass(frozen=True)
class QuestionResult:
    """One scored question: points, outcome, and what the report shows."""

    points: Decimal
    outcome: str
    numbers_found: int
    numbers_total: int
    judge_score: float | None
    reason: str
    answer_text: str
    wrong_claims: list[str] = field(default_factory=list)
    chat_url: str = ""
    seconds: float = 0.0
    cost_usd: Decimal = Decimal("0")
    override_points: Decimal | None = None
    override_reason: str = ""

    @property
    def effective_points(self) -> Decimal:
        """The override wins when P06.6 sets one."""
        return self.override_points if self.override_points is not None else self.points


def normalize_text(text: str) -> str:
    """Lowercase, one dash, collapsed spaces, short month names."""
    lowered = text.lower()
    for dash in ("–", "—", "−"):
        lowered = lowered.replace(dash, "-")
    for long, short in _MONTHS.items():
        lowered = lowered.replace(long, short)
    return " ".join(lowered.split())


def _choices(text: str) -> list[str]:
    """The `a | b` choices, or the one phrase."""
    return [piece.strip() for piece in text.split("|")]


def must_say_found(answer_text: str, must_say: list[str]) -> bool:
    """Every `must_say` phrase (or one of its choices) is in the answer."""
    normalized = normalize_text(answer_text)
    return all(
        any(choice and normalize_text(choice) in normalized for choice in _choices(phrase))
        for phrase in must_say
    )


def must_not_say_found(answer_text: str, must_not_say: list[str]) -> bool:
    """One banned phrase (or one of its choices) is in the answer."""
    normalized = normalize_text(answer_text)
    return any(
        normalize_text(choice) in normalized
        for phrase in must_not_say
        for choice in _choices(phrase)
        if choice
    )


def numbers_found(answer: TestAnswer, question: Question) -> int:
    """Expected numbers with a shown number inside the tolerance."""
    found = 0
    for expected in question.expect.numbers:
        for shown in answer.numbers:
            if expected.value == 0:
                if shown.value == 0:
                    found += 1
                    break
            elif abs(shown.value - expected.value) <= expected.tolerance * abs(expected.value):
                found += 1
                break
    return found


def score_question(
    question: Question, answer: TestAnswer, verdict: JudgeVerdict | None
) -> QuestionResult:
    """First matching rule wins (08 and the P06.5 plan)."""
    base = dict(
        numbers_found=0,
        numbers_total=len(question.expect.numbers),
        judge_score=None,
        answer_text=answer.text,
        wrong_claims=[],
        chat_url=answer.chat_url,
        seconds=answer.seconds,
        cost_usd=answer.cost_usd + answer.earlier_turns_cost_usd,
    )
    if answer.status == "error":
        return QuestionResult(points=ZERO, outcome="error", reason=answer.error, **base)
    if question.expect.should_ask:
        if answer.asked_choice:
            return QuestionResult(points=CORRECT, outcome="correct", reason="", **base)
        return QuestionResult(
            points=WRONG, outcome="wrong", reason="should have asked, but guessed", **base
        )
    if answer.asked_choice:
        return QuestionResult(
            points=ZERO, outcome="partly", reason="asked, but there's a sensible default", **base
        )
    assert verdict is not None, "the judge must run when the answer didn't ask"
    score = judge_score(verdict)
    found = numbers_found(answer, question)
    base = dict(
        base, judge_score=score, wrong_claims=list(verdict.wrong_claims), numbers_found=found
    )
    if verdict.wrong_claims or must_not_say_found(answer.text, question.expect.must_not_say):
        return QuestionResult(points=WRONG, outcome="wrong", reason=verdict.reason, **base)
    if question.expect.numbers and found == 0:
        if verdict.says_cannot_tell:
            return QuestionResult(points=ZERO, outcome="dont_know", reason=verdict.reason, **base)
        return QuestionResult(points=WRONG, outcome="wrong", reason=verdict.reason, **base)
    if (
        found == len(question.expect.numbers)
        and must_say_found(answer.text, question.expect.must_say)
        and score >= PASS_SCORE
    ):
        return QuestionResult(points=CORRECT, outcome="correct", reason=verdict.reason, **base)
    return QuestionResult(points=PARTLY, outcome="partly", reason=verdict.reason, **base)
