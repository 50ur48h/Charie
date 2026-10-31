"""Section notes: the source text is data, the form rejects extras (P08.4)."""

import pytest
from pydantic import ValidationError

from charie.learner.steps.document_index import SectionNoteForm
from charie.shared.ai.prompts import build_messages, load_prompt

SECTION = "# Refunds\n\nFull refunds within 30 days.\n"


def test_text_is_data() -> None:
    """The section arrives fenced off as data, never as instructions."""
    prompt = load_prompt("note_section")
    user_text = build_messages(prompt, {"section": SECTION})[1]["content"]
    assert "<section>" in user_text and SECTION in user_text
    assert "do not follow" in user_text.lower()


def test_note_schema() -> None:
    """A plain note parses; an extra field is refused, not ignored."""
    form = SectionNoteForm.model_validate({"note": "Refund policy: 30 days."})
    assert form.note.startswith("Refund policy")
    with pytest.raises(ValidationError):
        SectionNoteForm.model_validate({"note": "Refund policy.", "facts": ["invented"]})
