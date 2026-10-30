"""Scoring rules: first match wins, code decides the points (P06.5 plan)."""

from decimal import Decimal

import pytest

from tests.questions.answers import ShownNumber, TestAnswer
from tests.questions.format import Question
from tests.questions.judge import JudgeVerdict, judge_score
from tests.questions.scoring import (
    must_not_say_found,
    must_say_found,
    normalize_text,
    numbers_found,
    score_question,
)


def _question(**over) -> Question:
    fields = {
        "id": "clear-901",
        "kind": "clear",
        "question": "How many orders were there?",
        "expect": {"numbers": [{"name": "orders", "value": "100", "tolerance": "2"}]},
        "checked_by": "Muse Code, 2026-10-30",
        "why_fair": "A plain count.",
    }
    fields.update(over)
    return Question.model_validate(fields)


def _answer(text="orders: 100", numbers=None, asked=False, status="ok", error="") -> TestAnswer:
    if numbers is None:
        numbers = [ShownNumber(label="orders", value=Decimal("100"))]
    return TestAnswer(text=text, numbers=numbers, asked_choice=asked, status=status, error=error)


def _verdict(**over) -> JudgeVerdict:
    fields = {
        "answers_exactly": "yes",
        "explains": "yes",
        "mentions_what_matters": "yes",
        "no_unsupported_claims": "yes",
        "says_cannot_tell": False,
        "wrong_claims": [],
        "reason": "It answers directly.",
    }
    fields.update(over)
    return JudgeVerdict.model_validate(fields)


def test_correct() -> None:
    result = score_question(_question(), _answer("orders: 100"), _verdict())
    assert (result.points, result.outcome) == (Decimal(1), "correct")


def test_weak_explanation_is_partly() -> None:
    verdict = _verdict(explains="no", mentions_what_matters="partly")
    result = score_question(_question(), _answer("orders: 100"), verdict)
    assert (result.points, result.outcome) == (Decimal("0.5"), "partly")


def test_some_numbers_is_partly() -> None:
    question = _question(
        expect={
            "numbers": [
                {"name": "a", "value": "100", "tolerance": "0.005"},
                {"name": "b", "value": "200", "tolerance": "0.005"},
            ]
        }
    )
    result = score_question(question, _answer("a: 100"), _verdict())
    assert (result.points, result.outcome) == (Decimal("0.5"), "partly")


def test_missing_must_say_is_partly() -> None:
    question = _question(
        expect={
            "numbers": [{"name": "orders", "value": "100", "tolerance": "2"}],
            "must_say": ["December"],
        }
    )
    result = score_question(question, _answer("orders: 100"), _verdict())
    assert (result.points, result.outcome) == (Decimal("0.5"), "partly")


def test_cannot_tell_is_dont_know() -> None:
    verdict = _verdict(says_cannot_tell=True, reason="It says it cannot tell.")
    result = score_question(_question(), _answer("I cannot tell.", numbers=[]), verdict)
    assert (result.points, result.outcome) == (Decimal(0), "dont_know")


def test_no_numbers_and_confident_is_wrong() -> None:
    result = score_question(_question(), _answer("Lots of orders.", numbers=[]), _verdict())
    assert (result.points, result.outcome) == (Decimal(-1), "wrong")


def test_wrong_claim_is_wrong() -> None:
    verdict = _verdict(wrong_claims=["invented a trend"])
    result = score_question(_question(), _answer("orders: 100, and rising fast"), verdict)
    assert (result.points, result.outcome) == (Decimal(-1), "wrong")


def test_must_not_say_is_wrong() -> None:
    question = _question(
        expect={
            "numbers": [{"name": "orders", "value": "100", "tolerance": "2"}],
            "must_not_say": ["guestimate"],
        }
    )
    result = score_question(question, _answer("orders: 100, a guestimate"), _verdict())
    assert (result.points, result.outcome) == (Decimal(-1), "wrong")


def test_should_ask_and_asked() -> None:
    question = _question(expect={"should_ask": True})
    result = score_question(question, _answer("Which kind of best?", numbers=[], asked=True), None)
    assert (result.points, result.outcome) == (Decimal(1), "correct")


def test_should_ask_but_guessed() -> None:
    question = _question(expect={"should_ask": True})
    result = score_question(question, _answer("Rice is best.", numbers=[]), None)
    assert result.points == Decimal(-1)
    assert result.reason == "should have asked, but guessed"


def test_asked_without_need() -> None:
    result = score_question(_question(), _answer("Which month?", numbers=[], asked=True), None)
    assert result.points == Decimal(0)
    assert result.reason == "asked, but there's a sensible default"


def test_error_scores_zero() -> None:
    result = score_question(_question(), _answer(status="error", error="No saved reply."), None)
    assert (result.points, result.outcome) == (Decimal(0), "error")


def test_tolerance_edges() -> None:
    question = _question(expect={"numbers": [{"name": "n", "value": "100", "tolerance": "0.005"}]})
    inside = TestAnswer(text="n: 100.5", numbers=[ShownNumber(label="n", value=Decimal("100.5"))])
    outside = TestAnswer(text="n: 100.6", numbers=[ShownNumber(label="n", value=Decimal("100.6"))])
    assert numbers_found(inside, question) == 1
    assert numbers_found(outside, question) == 0


def test_zero_needs_exact_zero() -> None:
    question = _question(expect={"numbers": [{"name": "n", "value": "0", "tolerance": "2"}]})
    exact = TestAnswer(text="n: 0", numbers=[ShownNumber(label="n", value=Decimal("0"))])
    near = TestAnswer(text="n: 0.1", numbers=[ShownNumber(label="n", value=Decimal("0.1"))])
    assert numbers_found(exact, question) == 1
    assert numbers_found(near, question) == 0


def test_text_matching_rules() -> None:
    assert normalize_text("November  2025") == "nov 2025"
    assert normalize_text("well—known") == "well-known"
    assert must_say_found("Sales in November 2025", ["Nov 2025"])
    assert must_say_found("It took three days", ["3 days | three days | partial"])
    assert not must_say_found("Sales in 2025", ["Nov 2025"])
    assert must_not_say_found("A guestimate", ["guestimate"])
    assert not must_not_say_found("A careful count", ["guestimate"])


def test_judge_score_is_mean_of_rubric() -> None:
    verdict = _verdict(
        answers_exactly="yes",
        explains="partly",
        mentions_what_matters="no",
        no_unsupported_claims="yes",
    )
    assert judge_score(verdict) == pytest.approx(0.625)


def test_judge_score_all_yes_is_one() -> None:
    assert judge_score(_verdict()) == pytest.approx(1.0)
