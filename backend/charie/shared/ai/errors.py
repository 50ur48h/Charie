"""AI errors, all with a code and a plain message (architecture 03)."""


class AiError(Exception):
    """Base of every AI error. `code` travels to the screens and API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AiUnavailable(AiError):
    """The AI stayed busy or silent through every retry."""

    def __init__(self) -> None:
        super().__init__(
            "ai_unavailable",
            "The AI service didn't answer after 5 tries. Please try again in a few minutes.",
        )


class AiFormError(AiError):
    """The reply didn't match the job's form, even after the repair try."""

    def __init__(self, job: str) -> None:
        super().__init__(
            "ai_bad_answer",
            f"The AI's answer for `{job}` didn't match the required form, even after one retry.",
        )


class AiOutOfCredit(AiError):
    """Meta refused: the account is out of credit."""

    def __init__(self) -> None:
        super().__init__("ai_out_of_credit", "The AI account is out of credit.")


class AiApiError(AiError):
    """Meta refused the request for another reason."""

    def __init__(self, reason: str) -> None:
        super().__init__("ai_api_error", f"The AI service refused the request: `{reason}`.")


class SpendingPaused(AiError):
    """New AI work stops when the month's limit is reached."""

    def __init__(self) -> None:
        super().__init__(
            "spending_paused",
            "New AI work is paused because this month's spending limit is reached. "
            "Raise the limit on the Usage page to continue.",
        )


class AiReplayMissing(AiError):
    """Replay mode has no saved reply for this request."""

    def __init__(self, job: str, fingerprint: str) -> None:
        super().__init__(
            "ai_replay_missing",
            f"No saved AI reply for job `{job}` (`{fingerprint[:12]}`). "
            "Record it on the laptop with AI_REPLAY=record.",
        )


class AiRealCallBlocked(AiError):
    """A test tried to reach Meta without the `live_ai` mark."""

    def __init__(self) -> None:
        super().__init__(
            "ai_real_call_blocked",
            "This test tried to make a real AI call. "
            "Mark it with @pytest.mark.live_ai, or use FakeAi.",
        )
