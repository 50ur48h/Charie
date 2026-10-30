"""Every public answer key still matches the practice database (read-only)."""

from pathlib import Path

import pytest

from tests.questions.format import load_questions
from tests.questions.keys import key_matches, run_answer_key

PUBLIC = Path(__file__).resolve().parents[2] / "questions" / "public.yaml"


def _keyed():
    """Public questions with expected numbers, in file order."""
    return [question for question in load_questions(PUBLIC, "public") if question.expect.numbers]


@pytest.mark.practice_db
@pytest.mark.parametrize("question", _keyed(), ids=lambda question: question.id)
def test_answer_key_matches(question) -> None:
    assert key_matches(question, run_answer_key(question))
