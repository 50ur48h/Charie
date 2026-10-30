"""The P06.2 public set: 12 questions, the planned mix, 5 in smoke."""

from collections import Counter
from pathlib import Path

from tests.questions import check
from tests.questions.format import load_questions

PUBLIC = Path(__file__).resolve().parents[2] / "questions" / "public.yaml"


def test_public_file_is_valid(capsys) -> None:
    code = check.run(["--set", "public"])
    assert code == 0
    out = capsys.readouterr().out
    assert "public.yaml is valid: 12 questions (clear 4, trap 4, vague 4). Smoke: 5." in out


def test_public_mix() -> None:
    questions = load_questions(PUBLIC, "public")
    assert Counter(question.kind for question in questions) == {
        "clear": 4,
        "vague": 4,
        "trap": 4,
    }
    assert sum(1 for question in questions if question.smoke) == 5
