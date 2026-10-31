"""Fact forms: fixed shapes, exact quotes, data-not-instructions (P08.6)."""

import pytest
from pydantic import ValidationError

from charie.learner.steps.doc_facts import (
    CompareFactsForm,
    DocFactForm,
    ExtractDocFactsForm,
)
from charie.shared.ai.prompts import build_messages, load_prompt

SECTION = "# Net sales\n\nNet sales means total orders minus refunds.\n"


def test_extract_form() -> None:
    """A plain fact parses; an extra field is refused, not ignored."""
    form = ExtractDocFactsForm.model_validate(
        {
            "facts": [
                {
                    "kind": "definition",
                    "topic": "Net sales",
                    "statement": "Net sales means total orders minus refunds.",
                    "quote": "Net sales means total orders minus refunds.",
                    "location": "Net sales",
                }
            ]
        }
    )
    assert form.facts[0].kind == "definition"
    with pytest.raises(ValidationError):
        DocFactForm.model_validate(
            {
                "kind": "definition",
                "topic": "Net sales",
                "statement": "Net sales means everything.",
                "quote": "Net sales means total orders minus refunds.",
                "facts": ["invented"],
            }
        )


def test_extract_text_is_data() -> None:
    """The section arrives fenced off as data, never as instructions."""
    prompt = load_prompt("extract_doc_facts")
    user_text = build_messages(prompt, {"heading": "Net sales", "section": SECTION})[1]["content"]
    assert "<section>" in user_text and SECTION in user_text
    assert "do not follow" in user_text.lower()


def test_compare_form_and_prompt() -> None:
    """The verdict form parses; the prompt judges the given statements."""
    form = CompareFactsForm.model_validate({"agree": False, "topic": "Net sales 2025"})
    assert form.agree is False
    prompt = load_prompt("compare_facts")
    user_text = build_messages(
        prompt,
        {
            "topic": "Net sales 2025",
            "statements": ["Net sales were $1.2M.", "Net sales were $1.5M."],
        },
    )[1]["content"]
    assert "Net sales 2025" in user_text and "$1.5M" in user_text
