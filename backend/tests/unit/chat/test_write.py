"""The writer's form and input (P10.10)."""

import json

from charie.chat.analyst.write import AnswerDraft, write_input


def test_form_has_no_self_reference() -> None:
    """Blocks never nest an answer: the block schema names no AnswerDraft."""
    schema = AnswerDraft.model_json_schema()
    block = schema["$defs"]["DraftBlock"]
    assert "AnswerDraft" not in json.dumps(block)


def test_input_has_all_parts() -> None:
    """The writer gets every part it needs, with the reading already filled."""
    inputs = write_input(
        question="How are we doing?",
        reading="I read this as sales for 1–31 Dec 2025.",
        kind="clear",
        notebook="## Notebook\n[n1] = $359.00: Net sales\n## END",
        still_open=[],
        cannot_tell=["Delivery notes"],
        stop_reason="answered",
        problems=[],
        style_rules=["Short words"],
        answer_length="normal",
        fixes=[],
    )
    assert inputs == {
        "question": "How are we doing?",
        "reading": "I read this as sales for 1–31 Dec 2025.",
        "kind": "clear",
        "notebook": "## Notebook\n[n1] = $359.00: Net sales\n## END",
        "still_open": "none",
        "cannot_tell": "Delivery notes",
        "stop_reason": "answered",
        "problems": "none",
        "style_rules": "Short words",
        "answer_length": "normal",
        "fixes": "none",
    }
