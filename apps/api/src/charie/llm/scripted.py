"""A provider that answers from a fixed script, so CI can prove the stack (WP11.2b)."""

from __future__ import annotations

import json
import re

from charie.llm.base import Completion, LLMRequest, ProviderCaps, Usage

__all__ = ["PROVIDER_NAME", "SCRIPTED_SQL", "ScriptedProvider"]

PROVIDER_NAME = "scripted"

#: What the smoke's question resolves to.
SCRIPTED_SQL = "SELECT count(*) AS order_count FROM orders"

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _cited(prompt: str) -> list[str]:
    """The execution the composing prompt was shown, if it was shown one."""
    found = _UUID.search(prompt)
    return [found.group(0)] if found else []


def scripted_body(request: LLMRequest) -> str:
    """The scripted reply for this role, as the JSON the front door will parse."""
    role = request.tags.role
    if role == "sql":
        return json.dumps(
            {
                "sql": SCRIPTED_SQL,
                "purpose": "count the orders",
                "answerable": True,
            }
        )
    if role == "plan":
        # One iteration is enough: the smoke is about the path, not the search.
        return json.dumps({"done": True, "rationale": "that answers it"})
    if role == "critic":
        return json.dumps({"verdict": "pass"})
    if role == "compose":
        return json.dumps(
            {
                "answer": "The scripted model answered from a fixed script.",
                # No `answered`, and no `unanswered`.
                "supported_by": _cited(request.prompt_text),
                "confidence": "high",
            }
        )
    # Any other role — `intake`, `observe` — gets free text.
    return "A scripted reply."


class ScriptedProvider:
    """`LLMProvider`, answering from `scripted_body` and costing nothing."""

    def capabilities(self) -> ProviderCaps:
        return ProviderCaps(
            name=PROVIDER_NAME,
            # No native structured decoding: replies go through `llm/structured.py` like a...
            supports_response_schema=False,
            supports_system_message=True,
            is_stub=True,
        )

    async def complete(self, request: LLMRequest) -> Completion:
        return Completion(
            text=scripted_body(request),
            model=request.model,
            provider=PROVIDER_NAME,
            usage=Usage(input_tokens=0, output_tokens=0),
            latency_ms=0,
        )

    async def aclose(self) -> None:
        """Nothing to release: this provider opens no client."""
        return None
