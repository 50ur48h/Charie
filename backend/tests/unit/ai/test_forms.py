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
