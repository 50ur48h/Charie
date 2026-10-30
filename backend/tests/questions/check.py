"""Check the question files: kind counts, smoke, keys, and the hidden-file rule."""

import argparse
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from tests.questions.format import Question, QuestionFileError, load_questions
from tests.questions.keys import AnswerKeyError, key_matches, run_answer_key

REPO = Path(__file__).resolve().parents[3]


def _path_for(set_name: str, given: str | None) -> Path:
    """`--file` wins; otherwise the set's home from the repo root."""
    if given:
        return Path(given)
    if set_name == "public":
        return REPO / "backend" / "tests" / "questions" / "public.yaml"
    return REPO / "docs" / "hidden-tests" / "questions.yaml"


def _kinds_line(questions: list[Question]) -> str:
    """`(clear 4, trap 4)`: kind counts, kinds in alphabetical order."""
    counts = Counter(question.kind for question in questions)
    return "(" + ", ".join(f"{kind} {counts[kind]}" for kind in sorted(counts)) + ")"


def _list_table(questions: list[Question]) -> str:
    """One Markdown row per question: id, kind, smoke, chat, text, numbers."""

    def cell(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ")

    lines = [
        "| id | kind | smoke | chat | question | expected numbers | why_fair |",
        "|---|---|---|---|---|---|---|",
    ]
    for question in questions:
        numbers = "; ".join(
            f"{number.name} = {number.value} (±{number.tolerance})"
            for number in question.expect.numbers
        )
        lines.append(
            f"| {cell(question.id)} | {cell(question.kind)} | "
            f"{'yes' if question.smoke else 'no'} | {cell(' / '.join(question.chat))} | "
            f"{cell(question.question)} | {cell(numbers)} | {cell(question.why_fair)} |"
        )
    return "\n".join(lines)


def _run_keys(questions: list[Question]) -> int:
    """Run every key; 0 when each key matches, 1 when any key fails."""
    failed = False
    for question in questions:
        if not question.expect.numbers or not question.answer_key_sql.strip():
            print(f"{question.id}: has no key.")
            continue
        try:
            values: list[Decimal] = run_answer_key(question)
        except AnswerKeyError:
            print(f"{question.id}: the query failed.")
            failed = True
        else:
            if key_matches(question, values):
                print(f"{question.id}: matches.")
            else:
                print(f"{question.id}: doesn't match.")
                failed = True
    return 1 if failed else 0


def run(argv: list[str] | None = None) -> int:
    """Check one set; 0 when valid, 1 when not."""
    parser = argparse.ArgumentParser(description="Check a question file.")
    parser.add_argument("--set", required=True, choices=["public", "hidden"])
    parser.add_argument("--file", help="Check this file instead of the set's home.")
    parser.add_argument("--list", action="store_true", help="Print the set as a table.")
    parser.add_argument("--run-keys", action="store_true", help="Run every answer key.")
    args = parser.parse_args(argv)

    if args.list and args.set == "hidden":
        print("The hidden set is never listed.")
        return 1
    path = _path_for(args.set, args.file)
    if args.set == "hidden" and args.file is None and not path.exists():
        print("No hidden file yet. Follow P06.4 to create it.")
        return 0
    try:
        questions = load_questions(path, args.set)
    except OSError:
        print(f"Can't read {path}.")
        return 1
    except QuestionFileError as err:
        if args.set == "hidden":
            print(f"Your hidden file has {len(err.problems)} problems:")
        for problem in err.problems:
            print(problem)
        return 1
    if args.list:
        print(_list_table(questions))
        return 0
    if args.run_keys:
        return _run_keys(questions)
    smokes = sum(1 for question in questions if question.smoke)
    if args.set == "hidden":
        print(f"Your hidden file is valid: {len(questions)} questions {_kinds_line(questions)}.")
    else:
        print(
            f"{path.name} is valid: {len(questions)} questions "
            f"{_kinds_line(questions)}. Smoke: {smokes}."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Usage: check --set public|hidden [--file <path>] [--list] [--run-keys]."""
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
