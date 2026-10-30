"""The AI judge: scores how well a test answer explains (08, P06.5 plan)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from charie.shared.ai import get_ai
from charie.shared.ai.client import AiClient
from tests.questions.answers import TestAnswer
from tests.questions.format import Question

JOB = "judge_test_answer"

Rubric = Literal["yes", "partly", "no"]

KIND_GUIDANCE = {
    "clear": "A good answer states each expected number plainly.",
    "vague": "A good answer says how it read the vague question, then answers that reading.",
    "follow_up": "A good answer answers only the last question, using the earlier turns.",
    "why": "A good answer names the real driver in the data and never invents a reason.",
    "documents": "A good answer quotes the document and follows what it says.",
    "not_in_data": "A good answer says the data doesn't have this, and doesn't invent it.",
    "new_kind": "A good answer counts exactly what was asked, including an honest 0.",
    "trap": "A good answer avoids the tempting wrong reading and says what it ruled out.",
}


class JudgeVerdict(BaseModel):
    """The judge's flat form: 4 rubric fields, 3 extras (P06.5 plan)."""

    answers_exactly: Rubric = Field(description="The answer answers exactly what was asked.")
    explains: Rubric = Field(description="The answer explains why, not just the numbers.")
    mentions_what_matters: Rubric = Field(
        description="The answer mentions what matters for this kind of question."
    )
    no_unsupported_claims: Rubric = Field(
        description="Every claim is backed by the answer's own numbers."
    )
    says_cannot_tell: bool = Field(description="True when the answer honestly says it cannot tell.")
    wrong_claims: list[str] = Field(
        default_factory=list,
        description="Up to 5 short texts: claims the numbers don't support.",
        max_length=5,
    )
    reason: str = Field(description="1-2 sentences on why this verdict.")


def judge_score(verdict: JudgeVerdict) -> float:
    """Code averages the 4 rubric fields: yes 1, partly 1/2, no 0."""
    values = {
        "yes": 1.0,
        "partly": 0.5,
        "no": 0.0,
    }
    fields = (
        verdict.answers_exactly,
        verdict.explains,
        verdict.mentions_what_matters,
        verdict.no_unsupported_claims,
    )
    return sum(values[field] for field in fields) / len(fields)


def fake_verdict() -> JudgeVerdict:
    """The dry-run judge: the fake answer copies the key, so it passes."""
    return JudgeVerdict(
        answers_exactly="yes",
        explains="yes",
        mentions_what_matters="yes",
        no_unsupported_claims="yes",
        says_cannot_tell=False,
        wrong_claims=[],
        reason="Fake judge: the dry-run answer copies the key.",
    )


def _inputs(question: Question, answer: TestAnswer) -> dict[str, Any]:
    """The judge's task data. Never the answer key SQL."""
    return {
        "kind": question.kind,
        "kind_guidance": KIND_GUIDANCE[question.kind],
        "chat": list(question.chat),
        "question": question.question,
        "expected_numbers": [
            {"name": expected.name, "value": str(expected.value)}
            for expected in question.expect.numbers
        ],
        "must_say": list(question.expect.must_say),
        "must_not_say": list(question.expect.must_not_say),
        "answer_text": answer.text,
    }


def judge_answer(
    question: Question, answer: TestAnswer, client: AiClient | None = None
) -> JudgeVerdict:
    """Ask the judge through the shared AI layer, with `app = "tests"`."""
    own = client if client is not None else get_ai()
    return own.run(JOB, _inputs(question, answer), JudgeVerdict, app="tests")
