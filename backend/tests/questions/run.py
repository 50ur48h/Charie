"""The test runner: ask each question, score it, write a report (P06.5)."""

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from charie.shared.ai.client import AiClient, get_ai
from charie.shared.config import get_settings
from tests.questions.answers import TestAnswer, fake_answer
from tests.questions.charie_answer import NotReadyError, charie_answer
from tests.questions.format import Question, QuestionFileError, load_questions
from tests.questions.judge import JudgeVerdict, fake_verdict, judge_answer
from tests.questions.report import (
    RunReport,
    ScoredQuestion,
    effective,
    points_text,
    report_markdown,
    write_report,
)
from tests.questions.scoring import score_question

REPO = Path(__file__).resolve().parents[3]
REPORTS_DIR = REPO / "docs" / "test-reports"
HIDDEN_REPORTS_DIR = REPO / "docs" / "hidden-tests" / "reports"

# Rough cost of one fresh question (03): $1-3 per answer, $0.02-0.10 per judge call.
ANSWER_COST_USD = (Decimal("1.00"), Decimal("3.00"))
JUDGE_COST_USD = (Decimal("0.02"), Decimal("0.10"))

SPARK_MODEL = "muse-spark-1.3-contributor"
# Spark bands scale the Nov 2021 pilot ($3.01 Wonder for 3 questions,
# docs/test-reports/2026-11-01-public-some-2.md) by the contributor prices.
SPARK_ANSWER_COST_USD = (Decimal("0.02"), Decimal("0.10"))
SPARK_JUDGE_COST_USD = (Decimal("0.01"), Decimal("0.02"))
_MODEL_ANSWER_COST_USD = {SPARK_MODEL: SPARK_ANSWER_COST_USD}
_MODEL_JUDGE_COST_USD = {SPARK_MODEL: SPARK_JUDGE_COST_USD}

JudgeFunction = Callable[[Question, TestAnswer], JudgeVerdict]

PUBLIC_FILE = REPO / "backend" / "tests" / "questions" / "public.yaml"
HIDDEN_FILE = REPO / "docs" / "hidden-tests" / "questions.yaml"


def _dry_judge(question: Question, answer: TestAnswer) -> JudgeVerdict:
    """The dry-run judge never calls the AI."""
    _ = (question, answer)
    return fake_verdict()


def _error_answer(message: str) -> TestAnswer:
    """A failed answer: the scorer gives 0 with outcome `error`."""
    return TestAnswer(text="", status="error", error=message)


def run_questions(
    questions: list[Question],
    *,
    set_name: str,
    mode: str,
    kind: str | None,
    some: bool,
    answer: Callable[[Question, bool], TestAnswer],
    judge: JudgeFunction,
    started_at: datetime,
    total_seconds: float,
    private: bool,
    client: AiClient | None = None,
) -> RunReport:
    """Ask, judge and score every question; the caller prints and saves."""
    rows: list[ScoredQuestion] = []
    for question in questions:
        try:
            test_answer = answer(question, private)
        except NotReadyError:
            raise
        except Exception as err:  # noqa: BLE001 - any answer failure is an error row
            test_answer = _error_answer(f"The answer failed: {err}")
        verdict = None
        judge_cost = Decimal("0")
        needs_judge = (
            test_answer.status != "error"
            and not question.expect.should_ask
            and not test_answer.asked_choice
        )
        if needs_judge:
            before = client.month_spent(datetime.now(UTC)) if client is not None else Decimal("0")
            try:
                verdict = judge(question, test_answer)
            except Exception as err:  # noqa: BLE001 - any judge failure is an error row
                test_answer = replace(test_answer, status="error", error=f"The judge failed: {err}")
            finally:
                if client is not None:
                    judge_cost = client.month_spent(datetime.now(UTC)) - before
        result = score_question(question, test_answer, verdict)
        rows.append(
            ScoredQuestion(
                question_id=question.id,
                kind=question.kind,
                smoke=question.smoke,
                points=result.effective_points,
                outcome=result.outcome,
                numbers_found=result.numbers_found,
                numbers_total=result.numbers_total,
                judge_score=result.judge_score,
                reason=result.reason,
                answer_text=result.answer_text,
                wrong_claims=result.wrong_claims,
                chat_url=result.chat_url,
                seconds=test_answer.seconds,
                cost_usd=result.cost_usd + judge_cost,
                override_points=result.override_points,
                override_reason=result.override_reason,
            )
        )
    return RunReport(
        set_name=set_name,
        mode=mode,
        started_at=started_at,
        seconds=total_seconds,
        results=rows,
        kind=kind,
        some=some,
    )


def estimate(questions: list[Question], model: str = "muse-wonder-1.0") -> str:
    """What a fresh run of these questions costs, before the owner says yes."""
    answers = sum(1 + len(question.chat) for question in questions)
    judges = len(questions)
    answer_low, answer_high = _MODEL_ANSWER_COST_USD.get(model, ANSWER_COST_USD)
    judge_low, judge_high = _MODEL_JUDGE_COST_USD.get(model, JUDGE_COST_USD)
    low = answers * answer_low + judges * judge_low
    high = answers * answer_high + judges * judge_high
    picked = f" with {model}" if model != "muse-wonder-1.0" else ""
    return (
        f"Fresh run of {len(questions)} questions{picked} "
        f"({answers} answers, {judges} judge calls): about ${low:.2f}–{high:.2f}."
    )


def _select(set_name: str, kind: str | None, ids: list[str]) -> list[Question]:
    """Load the set and keep the requested kind and ids, in file order."""
    if set_name == "hidden":
        questions = load_questions(HIDDEN_FILE, "hidden")
    else:
        questions = load_questions(PUBLIC_FILE, "public")
    if set_name == "smoke":
        questions = [question for question in questions if question.smoke]
    if kind:
        questions = [question for question in questions if question.kind == kind]
    if ids:
        wanted = set(ids)
        questions = [question for question in questions if question.id in wanted]
    return questions


def _print_public(report: RunReport, markdown_path: Path) -> None:
    """The public screen: summary, score by kind, total, cost, report path."""
    text = report_markdown(report)
    summary = text.split("## Score by kind")[0]
    kinds = text.split("## Score by kind")[1].split("## Every question")[0]
    print(summary + "## Score by kind" + kinds + f"Report saved: {markdown_path}")


def _print_hidden(report: RunReport) -> None:
    """The hidden screen: ids and scores only, never any text."""
    for row in report.results:
        print(f"{row.question_id}  {row.kind}  {points_text(effective(row))}")
    text = report_markdown(report)
    kinds = text.split("## Score by kind")[1].split("## Every question")[0]
    print("## Score by kind" + kinds)
    print("Report saved in the hidden folder.")


def _apply_model_flags(args) -> None:
    """Pin the model and effort for this run via the environment."""
    os.environ["AI_MODEL"] = args.model
    os.environ["AI_REASONING_EFFORT"] = args.effort
    get_settings.cache_clear()


def main(argv: list[str] | None = None) -> int:
    """Run one set: --set smoke|public|hidden [--kind K] [--ids a,b] [--dry-run|--fresh]."""
    parser = argparse.ArgumentParser(description="Ask the test questions and score them.")
    parser.add_argument("--set", required=True, choices=["smoke", "public", "hidden"])
    parser.add_argument("--kind", help="Only this question kind.")
    parser.add_argument("--ids", help="Only these question ids, comma separated.")
    parser.add_argument("--dry-run", action="store_true", help="Fake answers, fake judge, $0.")
    parser.add_argument(
        "--fresh", action="store_true", help="Record real AI replies (costs money)."
    )
    parser.add_argument("--estimate", action="store_true", help="Print the fresh cost and stop.")
    parser.add_argument("--yes", action="store_true", help="The owner approved a fresh run.")
    parser.add_argument(
        "--model",
        default=SPARK_MODEL,
        help="The AI model for this run (Wonder stays one flag away: --model muse-wonder-1.0).",
    )
    parser.add_argument("--effort", default="high", help="Reasoning effort for this run.")
    args = parser.parse_args(argv)

    if args.set == "hidden" and not HIDDEN_FILE.exists():
        print("No hidden file yet. Follow P06.4 to create it.")
        return 0
    ids = [piece.strip() for piece in args.ids.split(",") if piece.strip()] if args.ids else []
    try:
        questions = _select(args.set, args.kind, ids)
    except (OSError, QuestionFileError) as err:
        print(err)
        return 1
    if not questions:
        print("No questions selected.")
        return 1

    if args.estimate:
        print(estimate(questions, args.model))
        return 0

    if args.fresh:
        _apply_model_flags(args)
        print(estimate(questions, args.model))
        approved = args.yes or (
            sys.stdin.isatty() and input("Run fresh? [yes/no] ").strip() == "yes"
        )
        if not approved:
            print("Fresh runs need a yes. Show the estimate, ask the owner, then add --yes.")
            return 1
        os.environ["AI_REPLAY"] = "record"
        if args.set == "hidden":
            os.environ["AI_REPLAY_DIR"] = "docs/hidden-tests/replays"
        mode = "fresh"
        answer_fn = charie_answer
        client: AiClient | None = get_ai()
    elif args.dry_run:
        mode = "dry-run"
        answer_fn = lambda question, private: fake_answer(question, {})  # noqa: E731
        client = None
    else:
        _apply_model_flags(args)
        os.environ["AI_REPLAY"] = "replay"
        if args.set == "hidden":
            os.environ["AI_REPLAY_DIR"] = "docs/hidden-tests/replays"
        mode = "replay"
        answer_fn = charie_answer
        client = get_ai()

    def _run_judge(question: Question, test_answer: TestAnswer) -> JudgeVerdict:
        if client is None:
            return _dry_judge(question, test_answer)
        return judge_answer(question, test_answer, client)

    judge_fn: JudgeFunction = _run_judge

    private = args.set == "hidden"
    started_at = datetime.now(UTC)
    started = time.monotonic()
    try:
        report = run_questions(
            questions,
            set_name=args.set,
            mode=mode,
            kind=args.kind,
            some=bool(ids),
            answer=answer_fn,
            judge=judge_fn,
            started_at=started_at,
            total_seconds=0.0,
            private=private,
            client=client,
        )
    except NotReadyError as err:
        print(err)
        return 1
    total = time.monotonic() - started
    report = RunReport(
        set_name=report.set_name,
        mode=report.mode,
        started_at=report.started_at,
        seconds=total,
        results=report.results,
        kind=report.kind,
        some=report.some,
    )
    folder = HIDDEN_REPORTS_DIR if private else REPORTS_DIR
    markdown_path, _ = write_report(report, folder, datetime.now(UTC))
    if private:
        _print_hidden(report)
    else:
        _print_public(report, markdown_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
