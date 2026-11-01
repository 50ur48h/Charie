"""JSON forms: strict schemas Meta takes, and refusals it doesn't."""

from enum import StrEnum
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from charie.shared.ai.errors import AiError
from charie.shared.ai.forms import FormError, form_schema


class Kind(StrEnum):
    FACT = "fact"
    NOTE = "note"


class Item(BaseModel):
    label: str = Field(description="The label, like [n1].")
    kind: Kind = Field(description="What kind of item it is.")


class Answer(BaseModel):
    title: str = Field(description="A short title.")
    count: int = Field(description="How many.")
    items: list[Item] = Field(description="The items.")


def test_schema_is_strict():
    schema = form_schema(Answer)
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["count", "items", "title"]
    assert "$defs" not in schema


def test_nested_models_are_inlined():
    schema = form_schema(Answer)
    item = schema["properties"]["items"]["items"]
    assert item["additionalProperties"] is False
    assert item["required"] == ["kind", "label"]


def test_self_referring_form_refused():
    class Node(BaseModel):
        name: str = Field(description="The name.")
        child: "Node | None" = Field(default=None, description="The child.")

    with pytest.raises(FormError, match="refers to itself"):
        form_schema(Node)


def test_field_without_description_refused():
    class Sloppy(BaseModel):
        title: str

    with pytest.raises(FormError, match="`Sloppy.title` needs a one-line description"):
        form_schema(Sloppy)


def test_literal_becomes_enum():
    class Pick(BaseModel):
        choice: Literal["a", "b"] = Field(description="The pick.")

    schema = form_schema(Pick)
    assert schema["properties"]["choice"]["enum"] == ["a", "b"]


def test_bad_form_is_an_ai_error():
    assert issubclass(FormError, AiError)


def test_bare_dict_refused():
    class Vague(BaseModel):
        proposal: dict = Field(default={}, description="Machine-readable bits.")

    with pytest.raises(FormError, match="free-form object"):
        form_schema(Vague)


def test_write_questions_form_is_strict():
    from charie.shared.knowledge.questions import WriteQuestionsForm

    schema = form_schema(WriteQuestionsForm)

    def check(node, path):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, path
            for key, value in node.items():
                check(value, f"{path}.{key}")
        elif isinstance(node, list):
            for position, value in enumerate(node):
                check(value, f"{path}[{position}]")

    check(schema, "WriteQuestionsForm")
    reply = WriteQuestionsForm.model_validate(
        {
            "questions": [
                {
                    "topic": "What sales means",
                    "title": "What should sales mean?",
                    "body": "This decides which number sales questions use.",
                    "options": [
                        {
                            "id": "a",
                            "label": "Net sales",
                            "explanation": "Completed orders.",
                            "proposal": {"metric": "metric.net_sales"},
                        },
                        {
                            "id": "b",
                            "label": "Use the calendar",
                            "explanation": "Weeks start Monday.",
                            "proposal": {
                                "calendar": {
                                    "time_zone": "America/Chicago",
                                    "week_start": "monday",
                                    "fiscal_year_start": 1,
                                }
                            },
                        },
                    ],
                    "default_option": "a",
                }
            ]
        }
    )
    assert reply.questions[0].options[0].proposal.metric == "metric.net_sales"
    assert reply.questions[0].options[1].proposal.calendar.week_start == "monday"
