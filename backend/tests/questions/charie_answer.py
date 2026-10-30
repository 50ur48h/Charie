"""Charie's real answer function (built in P10.14)."""

from tests.questions.answers import TestAnswer
from tests.questions.format import Question


class NotReadyError(Exception):
    """The real answer function isn't built yet; only `--dry-run` works."""


def charie_answer(question: Question, private: bool) -> TestAnswer:
    """Run Charie in this same process (so it follows `AI_REPLAY`).

    Ask the `chat` lines, then the question, in one new chat; on an earlier
    turn, a quick question gets the first option. `text` is the whole final
    answer as plain text, "I read this as..." included. `numbers` are the `ok`
    notebook numbers whose labels the answer shows. `asked_choice` is true
    when the final message is `needs_choice`. `private=True` (hidden set)
    deletes the chat afterwards and saves no memories.
    """
    _ = (question, private)
    raise NotReadyError("The real answer function arrives in P10.14. Use --dry-run for now.")
