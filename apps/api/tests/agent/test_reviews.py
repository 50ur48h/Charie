import pytest

from charie.agent.reviews import brief_requested, review_requested


@pytest.mark.parametrize(
    "question",
    [
        "Prepare a monthly business review",
        "Give me a performance overview",
        "How are we doing this month?",
        "How we did in december 2025?",
        "How did we perform last month?",
        "How are sales doing this month?",
        "How was our business in December?",
    ],
)
def test_reviews_receive_the_report_contract(question: str) -> None:
    assert review_requested(question)


@pytest.mark.parametrize(
    "question", ["How many orders?", "How are you doing?", "Show sales by day"]
)
def test_narrow_questions_do_not_require_an_entire_review(question: str) -> None:
    assert not review_requested(question)


@pytest.mark.parametrize(
    "brevity", ["Short answer", "Briefly", "Keep it concise", "One sentence", "Just the number"]
)
def test_explicit_brevity_overrides_the_review(brevity: str) -> None:
    question = f"How did we do in December 2025? {brevity}."
    assert brief_requested(question)
    assert not review_requested(question)
