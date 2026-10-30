"""The question format: loader, file rules, and error messages."""

from pathlib import Path

import pytest

from tests.questions.format import QuestionFileError, load_questions

FIXTURES = Path(__file__).parent / "fixtures"


def _problems(name: str, set_name: str = "public") -> list[str]:
    with pytest.raises(QuestionFileError) as caught:
        load_questions(FIXTURES / name, set_name)
    return caught.value.problems


def test_good_public_file_loads() -> None:
    questions = load_questions(FIXTURES / "good_public.yaml", "public")
    assert [question.id for question in questions] == ["clear-001", "vague-001"]
    assert questions[0].expect.numbers[0].value == 33805
    assert questions[0].smoke is True


def test_bad_kind_and_unknown_field() -> None:
    problems = _problems("bad_enum.yaml")
    assert (
        "Question 1 (id clear-001): kind: must be one of: clear, vague, follow_up, "
        "why, documents, not_in_data, new_kind, trap." in problems
    )
    assert "Question 1 (id clear-001): frobnicate: is not a known field." in problems


def test_bad_tolerance_float() -> None:
    assert _problems("bad_tolerance.yaml") == [
        "Question 1 (id clear-001): expect.numbers[0].tolerance: must be a number."
    ]


def test_bad_should_ask() -> None:
    problems = _problems("bad_should_ask.yaml")
    assert "Question 1 (id vague-001): should_ask questions have no expected numbers." in problems


def test_bad_id_prefix() -> None:
    problems = _problems("bad_id_prefix.yaml")
    assert "Question 1 (id vague-001): id must look like `clear-001`." in problems


def test_bad_smoke_in_hidden_file() -> None:
    problems = _problems("bad_smoke_hidden.yaml", "hidden")
    assert "Question 1 (id h01): hidden questions are never smoke." in problems


def test_bad_duplicate_ids() -> None:
    problems = _problems("bad_duplicate_ids.yaml")
    assert "Question 2 (id clear-001): id is already used." in problems


def test_hidden_messages_never_show_values() -> None:
    problems = _problems("bad_hidden_secret.yaml", "hidden")
    assert problems
    assert all("SECRETWORD" not in problem for problem in problems)
