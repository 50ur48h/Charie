"""FakeAi: queued replies for other code's unit tests (no network)."""

from typing import Any

from pydantic import BaseModel

from charie.shared.ai.errors import AiError
from charie.shared.ai.provider import AiReply


class FakeAi:
    """`reply(job, data)` queues a reply; `fail(job, error)` queues an error."""

    def __init__(self) -> None:
        self.queued: dict[str, list[Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def reply(self, job: str, data: dict[str, Any] | BaseModel) -> "FakeAi":
        if isinstance(data, BaseModel):
            data = data.model_dump()
        self.queued.setdefault(job, []).append(data)
        return self

    def fail(self, job: str, error: Exception) -> "FakeAi":
        self.queued.setdefault(job, []).append(error)
        return self

    def complete(self, request) -> AiReply:
        job = request.job
        self.calls.append((job, list(request.messages)))
        if job not in self.queued or not self.queued[job]:
            raise AiError("fake_empty", f"FakeAi has no reply queued for job `{job}`.")
        next_item = self.queued[job].pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        import json

        return AiReply(
            content=json.dumps(next_item, sort_keys=True),
            prompt_tokens=100,
            cached_tokens=0,
            completion_tokens=20,
            reasoning_tokens=0,
            model=request.model,
        )
