"""Getting an object back from something that emits text."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from charie.llm.base import LLMError, Message

__all__ = [
    "StructuredOutputError",
    "instruction_for",
    "parse",
    "repair_messages",
]

#: A fenced block, with or without a language tag.
_FENCE = re.compile(r"```(?:[a-zA-Z0-9_-]+)?\s*(.*?)```", re.DOTALL)


class StructuredOutputError(LLMError):
    """The reply did not become the object the caller asked for."""

    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


def instruction_for(schema: type[BaseModel]) -> Message:
    """The system message that asks for JSON of a given shape."""
    body = json.dumps(schema.model_json_schema(), sort_keys=True)
    return Message(
        role="system",
        content=(
            "Reply with a single JSON object and nothing else — no prose before "
            "or after it. It must validate against this JSON Schema:\n" + body
        ),
    )


def parse[ModelT: BaseModel](schema: type[ModelT], text: str) -> ModelT:
    """The reply as an object, or ``StructuredOutputError`` saying what was wrong."""
    candidate = _extract(text)
    if candidate is None:
        raise StructuredOutputError(
            "the reply contained no JSON object. Reply with a single JSON object and nothing else."
        )
    try:
        payload: object = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise StructuredOutputError(
            f"the reply is not valid JSON: {error.msg} at position {error.pos}."
        ) from None
    # No "is it a dict" check: ``_extract`` only ever returns text starting with ``{``.
    try:
        return schema.model_validate(payload)
    except ValidationError as error:
        raise StructuredOutputError(
            "the JSON does not match the required shape: " + _readable(error)
        ) from None


def repair_messages(
    previous: list[Message], *, reply: str, problem: str, schema: type[BaseModel]
) -> list[Message]:
    """The conversation for the one repair attempt."""
    return [
        *previous,
        Message(role="assistant", content=reply),
        Message(
            role="user",
            content=(
                f"That reply could not be used: {problem}\n"
                "Reply again with only a single JSON object matching this JSON "
                "Schema, and no other text:\n"
                + json.dumps(schema.model_json_schema(), sort_keys=True)
            ),
        ),
    ]


def _extract(text: str) -> str | None:
    """The JSON object inside a reply, whatever it is wrapped in."""
    stripped = text.strip()
    if not stripped:
        return None

    fenced = _FENCE.search(stripped)
    if fenced is not None:
        stripped = fenced.group(1).strip()

    if stripped.startswith("{"):
        return stripped

    # Prose around one object: take from the first brace to the last.
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    return stripped[start : end + 1]


def _readable(error: ValidationError) -> str:
    """A pydantic error as one line a model can act on."""
    parts = [
        f"{'.'.join(str(item) for item in problem['loc']) or '(root)'}: {problem['msg']}"
        for problem in error.errors()[:5]
    ]
    return "; ".join(parts)
