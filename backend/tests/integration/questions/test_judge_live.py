"""One real judge call, under $0.10 (P06.5 Task 3)."""

import pytest

from tests.questions.answers import ShownNumber, TestAnswer
from tests.questions.format import Question
from tests.questions.judge import judge_answer


@pytest.mark.live_ai
def test_judge_real_call() -> None:
    question = Question.model_validate(
        {
            "id": "clear-902",
            "kind": "clear",
            "question": "How many orders were there in December 2025?",
            "expect": {
                "numbers": [{"name": "orders", "value": "25064", "tolerance": "2"}],
                "must_say": ["Dec 2025"],
            },
            "checked_by": "Muse Code, 2026-10-30",
            "why_fair": "A plain count.",
        }
    )
    answer = TestAnswer(
        text="orders: 25064. Dec 2025.",
        numbers=[ShownNumber(label="orders", value=25064)],
    )
    verdict = judge_answer(question, answer)
    assert verdict.answers_exactly == "yes"
    assert verdict.reason
