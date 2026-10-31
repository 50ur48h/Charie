"""P08.7 mix: five document questions, smoke stays ten with documents in it."""

from pathlib import Path

from tests.questions.format import load_questions

PUBLIC = Path(__file__).resolve().parents[2] / "questions" / "public.yaml"


def test_document_count_five() -> None:
    questions = load_questions(PUBLIC, "public")
    assert [question.id for question in questions if question.kind == "documents"] == [
        "documents-001",
        "documents-002",
        "documents-003",
        "documents-004",
        "documents-005",
    ]


def test_smoke_ten() -> None:
    questions = load_questions(PUBLIC, "public")
    smoked = [question for question in questions if question.smoke]
    assert len(smoked) == 10
    assert any(question.kind == "documents" for question in smoked)
