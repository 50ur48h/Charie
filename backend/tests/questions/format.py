"""One test question before it runs: the format, the loader, and the checker."""

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Kind = Literal["clear", "vague", "follow_up", "why", "documents", "not_in_data", "new_kind", "trap"]
KINDS = list(get_args(Kind))

_CHECKED_BY = re.compile(r"[^,]+, \d{4}-\d{2}-\d{2}")


def _decimal(value: object) -> Decimal:
    """An exact decimal; int and digits pass, float and the rest refuse."""
    if isinstance(value, (bool, float)):
        raise ValueError("must be a number")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("must be a number") from None


class ExpectedNumber(BaseModel):
    """One number the checker looks for: name, exact value, tolerance."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: Decimal
    tolerance: Decimal = Field(default=Decimal("0.005"), ge=Decimal(0))

    _as_decimal = field_validator("value", "tolerance", mode="before")(_decimal)


class Expect(BaseModel):
    """Everything the scorer checks: numbers, labels, traps, or a question."""

    model_config = ConfigDict(extra="forbid")

    numbers: list[ExpectedNumber] = []
    must_say: list[str] = []
    must_not_say: list[str] = []
    should_ask: bool = False


class Question(BaseModel):
    """One question in either file: the format 08-testing-plan describes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Kind
    smoke: bool = False
    chat: list[str] = []
    question: str = Field(min_length=1)
    expect: Expect = Expect()
    answer_key_sql: str = ""
    checked_by: str
    why_fair: str = ""


class QuestionFileError(Exception):
    """Every problem in a question file, one per line, with no file values."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = list(problems)


def _location(loc: tuple) -> str:
    """`expect.numbers[0].tolerance` from a Pydantic error location."""
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + str(part)
    return out


def _words(error: dict) -> str:
    """The fixed words for a Pydantic error type; never a file value."""
    kind = error["type"]
    if kind == "missing":
        return "is missing."
    if kind == "extra_forbidden":
        return "is not a known field."
    if kind == "literal_error":
        return f"must be one of: {', '.join(KINDS)}."
    if kind == "string_type":
        return "must be text."
    if kind == "string_too_short":
        return "must not be empty."
    if kind == "list_type":
        return "must be a list."
    if kind == "greater_than_equal":
        return "is not valid."
    if kind == "value_error":
        message = error.get("msg", "")
        tail = message.split(", ", 1)[1] if ", " in message else message
        if tail.rstrip(".") in {"must be a number"}:
            return tail if tail.endswith(".") else tail + "."
    return "is not valid."


def _tag(index: int, raw: object) -> str:
    """`Question 3 (id clear-003)`; `?` when the id itself is broken."""
    if isinstance(raw, dict):
        found = raw.get("id")
        if isinstance(found, str) and found:
            return f"Question {index + 1} (id {found})"
    return f"Question {index + 1} (id ?)"


def load_questions(path: str | Path, set_name: str) -> list[Question]:
    """Read and check a whole question file; every problem is reported."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is None:
        data = []
    if not isinstance(data, list):
        raise QuestionFileError(["The file must hold a list of questions."])
    problems: list[str] = []
    questions: list[Question] = []
    seen: set[str] = set()
    smokes = 0
    for index, raw in enumerate(data):
        tag = _tag(index, raw)
        if not isinstance(raw, dict):
            problems.append(f"{tag}: is not valid.")
            continue
        found_id = raw.get("id")
        if isinstance(found_id, str) and found_id:
            if found_id in seen:
                problems.append(f"{tag}: id is already used.")
            else:
                seen.add(found_id)
            kind = raw.get("kind")
            if isinstance(kind, str):
                if set_name == "public" and not re.fullmatch(re.escape(kind) + r"-\d{3}", found_id):
                    problems.append(f"{tag}: id must look like `{kind}-001`.")
                if set_name == "hidden" and not re.fullmatch(r"h\d{2}", found_id):
                    problems.append(f"{tag}: id must look like `h01`.")
        try:
            question = Question.model_validate(raw)
        except ValidationError as err:
            for error in err.errors(include_url=False):
                problems.append(f"{tag}: {_location(error['loc'])}: {_words(error)}")
            continue
        if question.kind == "follow_up" and not question.chat:
            problems.append(f"{tag}: follow_up questions need at least one chat line.")
        if question.expect.should_ask and question.expect.numbers:
            problems.append(f"{tag}: should_ask questions have no expected numbers.")
        if (
            question.expect.numbers
            and question.kind != "documents"
            and not question.answer_key_sql.strip()
        ):
            problems.append(f"{tag}: answer_key_sql is missing.")
        if question.checked_by and not _CHECKED_BY.fullmatch(question.checked_by):
            problems.append(f"{tag}: checked_by must look like `Name, 2026-11-05`.")
        if set_name == "public" and not question.why_fair.strip():
            problems.append(f"{tag}: why_fair is missing.")
        if set_name == "hidden" and question.smoke:
            problems.append(f"{tag}: hidden questions are never smoke.")
        if question.smoke:
            smokes += 1
            if smokes > 10:
                problems.append(f"{tag}: there are already 10 smoke questions.")
        questions.append(question)
    if problems:
        raise QuestionFileError(problems)
    return questions
