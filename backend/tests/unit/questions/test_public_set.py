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
    assert "public.yaml is valid: 23 questions " in out
    assert "Smoke: 10." in out


def test_public_mix() -> None:
    questions = load_questions(PUBLIC, "public")
    assert Counter(question.kind for question in questions) == {
        "clear": 4,
        "vague": 4,
        "trap": 4,
        "follow_up": 4,
        "why": 3,
        "not_in_data": 2,
        "new_kind": 2,
    }
    assert sum(1 for question in questions if question.smoke) == 10


def test_smoke_covers_every_kind_but_documents() -> None:
    questions = load_questions(PUBLIC, "public")
    smoked = {question.kind for question in questions if question.smoke}
    kinds = {question.kind for question in questions}
    assert smoked == kinds - {"documents"}
