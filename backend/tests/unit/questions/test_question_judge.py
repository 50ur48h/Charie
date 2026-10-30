"""The AI judge through a fake client: key and answer sent, verdict parses."""

from charie.shared.ai.client import AiClient
from charie.shared.ai.cost_log import MemoryCostLog
from charie.shared.ai.fake import FakeAi
from tests.questions.answers import ShownNumber, TestAnswer
from tests.questions.format import Question
from tests.questions.judge import judge_answer


def _question() -> Question:
    return Question.model_validate(
        {
            "id": "clear-901",
            "kind": "clear",
            "question": "How many orders were there in December 2025?",
            "expect": {
                "numbers": [{"name": "orders", "value": "25064", "tolerance": "2"}],
                "must_say": ["Dec 2025"],
            },
            "checked_by": "Muse Code, 2026-10-30",
            "why_fair": "A plain count.",
        }
    )


def _answer() -> TestAnswer:
    return TestAnswer(
        text="orders: 25064. Dec 2025.",
        numbers=[ShownNumber(label="orders", value=25064)],
    )


def test_judge_with_fake_ai_client() -> None:
    fake = FakeAi()
    fake.reply(
        "judge_test_answer",
        {
            "answers_exactly": "yes",
            "explains": "partly",
            "mentions_what_matters": "yes",
            "no_unsupported_claims": "yes",
            "says_cannot_tell": False,
            "wrong_claims": [],
            "reason": "It answers December directly but explains little.",
        },
    )
    log = MemoryCostLog()
    client = AiClient(provider=fake, cost_log=log, sleep=lambda s: None)
    verdict = judge_answer(_question(), _answer(), client)
    assert verdict.answers_exactly == "yes"
    assert verdict.reason.startswith("It answers December")
    job, messages = fake.calls[0]
    assert job == "judge_test_answer"
    assert messages
    assert log.rows[0]["app"] == "tests"
