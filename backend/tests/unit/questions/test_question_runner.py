"""The runner: dry runs score, estimates count turns, fresh needs a yes."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from tests.questions import run as run_module
from tests.questions.answers import ShownNumber, TestAnswer, fake_answer
from tests.questions.charie_answer import NotReadyError, charie_answer
from tests.questions.format import Question, load_questions
from tests.questions.judge import JudgeVerdict, fake_verdict
from tests.questions.report import report_markdown
from tests.questions.run import estimate, run_questions

FIXTURES = Path(__file__).parent / "fixtures"
MINI_START = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)


def _mini():
    """Mini questions with their fake answers and verdicts."""
    questions = load_questions(FIXTURES / "mini.yaml", "public")
    fakes = yaml.safe_load((FIXTURES / "mini_fake.yaml").read_text(encoding="utf-8"))

    def answer(question: Question, private: bool) -> TestAnswer:
        _ = private
        raw = fakes[question.id]["answer"]
        return TestAnswer(
            text=raw["text"],
            numbers=[
                ShownNumber(label=item["label"], value=Decimal(item["value"]))
                for item in raw["numbers"]
            ],
            asked_choice=raw["asked_choice"],
            status=raw["status"],
            error=raw["error"],
            seconds=raw["seconds"],
        )

    def judge(question: Question, test_answer: TestAnswer) -> JudgeVerdict:
        _ = (question, test_answer)
        raw = fakes[question.id]["verdict"]
        if raw == "fake":
            return fake_verdict()
        return JudgeVerdict.model_validate(raw)

    return questions, answer, judge


def test_fake_answer_copies_the_key() -> None:
    question = load_questions(FIXTURES / "mini.yaml", "public")[0]
    answer = fake_answer(question, {})
    assert [shown.value for shown in answer.numbers] == [Decimal("100")]
    assert answer.asked_choice is False
    assert answer.cost_usd == Decimal("0")
    assert "December" in answer.text


def test_dry_run_report_matches_expected() -> None:
    questions, answer, judge = _mini()
    report = run_questions(
        questions,
        set_name="mini",
        mode="dry-run",
        kind=None,
        some=False,
        answer=answer,
        judge=judge,
        started_at=MINI_START,
        total_seconds=5.0,
        private=False,
    )
    expected = (FIXTURES / "mini_report.md").read_text(encoding="utf-8")
    assert report_markdown(report) + "\n" == expected


def test_public_dry_run_scores_best_total() -> None:
    from tests.questions.run import _dry_judge

    questions = load_questions(
        Path(__file__).resolve().parents[2] / "questions" / "public.yaml", "public"
    )
    report = run_questions(
        questions,
        set_name="public",
        mode="dry-run",
        kind=None,
        some=False,
        answer=lambda question, private: fake_answer(question, {}),
        judge=_dry_judge,
        started_at=MINI_START,
        total_seconds=0.0,
        private=False,
    )
    assert sum(row.points for row in report.results) == len(questions) == 23


def test_hidden_output_shows_only_ids_and_scores(capsys) -> None:
    questions = load_questions(FIXTURES / "good_hidden.yaml", "hidden")
    report = run_questions(
        questions,
        set_name="hidden",
        mode="dry-run",
        kind=None,
        some=False,
        answer=lambda question, private: fake_answer(question, {}),
        judge=lambda question, test_answer: fake_verdict(),
        started_at=MINI_START,
        total_seconds=0.0,
        private=True,
    )
    run_module._print_hidden(report)
    out = capsys.readouterr().out
    assert "delivered" not in out
    assert "And in November?" not in out
    assert "h01  clear  1" in out
    assert "h02  follow_up  1" in out


def test_estimate_counts_earlier_turns() -> None:
    from tests.questions.run import _select

    smoke = _select("smoke", None, [])
    assert len(smoke) == 10
    assert (
        estimate(smoke) == "Fresh run of 10 questions (12 answers, 10 judge calls): about $12–37."
    )


def test_fresh_needs_a_yes(capsys) -> None:
    code = run_module.main(["--set", "smoke", "--fresh"])
    assert code == 1
    assert "Fresh runs need a yes." in capsys.readouterr().out


def test_real_answers_not_ready() -> None:
    question = load_questions(FIXTURES / "mini.yaml", "public")[0]
    with pytest.raises(NotReadyError):
        charie_answer(question, False)


def test_report_names_never_overwrite(tmp_path) -> None:
    from tests.questions.report import write_report

    questions, answer, judge = _mini()
    report = run_questions(
        questions,
        set_name="mini",
        mode="dry-run",
        kind=None,
        some=False,
        answer=answer,
        judge=judge,
        started_at=MINI_START,
        total_seconds=5.0,
        private=False,
    )
    first_md, first_json = write_report(report, tmp_path, MINI_START)
    second_md, second_json = write_report(report, tmp_path, MINI_START)
    assert first_md.name == "2026-10-30-mini-dry-run.md"
    assert second_md.name == "2026-10-30-mini-dry-run-2.md"
    assert first_md.exists() and second_md.exists()
    assert first_json.exists() and second_json.exists()
