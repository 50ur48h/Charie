"""Everything the scripted provider emits is a shape the product will accept."""

from __future__ import annotations

import json
import uuid
from typing import Any, cast

import pytest
from pydantic import BaseModel

from charie.agent.critic import CriticOut
from charie.agent.loop import Reflection
from charie.agent.planner import Plan
from charie.agent.tools.finalize import FinalizeIn
from charie.llm.base import LLMRequest, Message, Tags
from charie.llm.scripted import scripted_body

#: Each role the scripted provider answers structurally.
STRUCTURED_ROLES: list[tuple[str, type[BaseModel]]] = [
    ("sql", Plan),
    ("plan", Reflection),
    ("critic", CriticOut),
    ("compose", FinalizeIn),
]


def _reply(role: str) -> str:
    """What the provider says for a role, given a prompt that names an execution."""
    request = LLMRequest(
        model="scripted-1",
        messages=[
            Message(
                role="user",
                content="execution 3f7c1a02-5d21-4a9b-8c33-9e1f0b6d4a77 returned 3 rows",
            )
        ],
        tags=Tags(org_id=uuid.uuid4(), role=cast("Any", role), run_id=uuid.uuid4()),
    )
    return scripted_body(request)


@pytest.mark.parametrize(("role", "model"), STRUCTURED_ROLES, ids=[r for r, _ in STRUCTURED_ROLES])
def test_the_scripted_reply_validates(role: str, model: type[BaseModel]) -> None:
    """`extra="forbid"` is the reason this matters."""
    model.model_validate(json.loads(_reply(role)))


def test_the_composed_reply_cites_what_the_prompt_named() -> None:
    """The control on `_reply`'s uuid."""
    draft = FinalizeIn.model_validate(json.loads(_reply("compose")))

    assert draft.supported_by == ["3f7c1a02-5d21-4a9b-8c33-9e1f0b6d4a77"]
