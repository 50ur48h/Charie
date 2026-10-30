"""Check the question files: kind counts, smoke, and the hidden-file rule."""

import argparse
import sys
from collections import Counter
from pathlib import Path

from tests.questions.format import Question, QuestionFileError, load_questions

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


def run(argv: list[str] | None = None) -> int:
    """Check one set; 0 when valid, 1 when not."""
    parser = argparse.ArgumentParser(description="Check a question file.")
    parser.add_argument("--set", required=True, choices=["public", "hidden"])
    parser.add_argument("--file", help="Check this file instead of the set's home.")
    args = parser.parse_args(argv)

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
    """Usage: check --set public|hidden [--file <path>]."""
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
