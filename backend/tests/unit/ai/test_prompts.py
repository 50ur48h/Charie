"""Prompt files: 3 sections, stable parts first, filled task last."""

import pytest

from charie.shared.ai.errors import AiError
from charie.shared.ai.prompts import build_messages, load_prompt


def test_three_sections_needed(tmp_path):
    (tmp_path / "broken.md").write_text("## Rules\n1. Be brief.\n", encoding="utf-8")
    with pytest.raises(AiError, match="missing section `## Examples`"):
        load_prompt("broken", tmp_path)


def test_missing_prompt_file_message(tmp_path):
    with pytest.raises(AiError, match=r"There's no prompt file for job `nope`: .*nope\.md"):
        load_prompt("nope", tmp_path)


def test_stable_parts_first(prompts_dir):
    prompt = load_prompt("name_chat", prompts_dir)
    messages = build_messages(prompt, {"topic": "sales"})
    assert messages[0]["role"] == "system"
    assert "1. Short titles." in messages[0]["content"]
    assert "None." in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "Title this: sales."}


def test_stable_parts_first_with_knowledge(prompts_dir):
    prompt = load_prompt("name_chat", prompts_dir)
    messages = build_messages(prompt, {"topic": "sales"}, knowledge_summary="Net sales is [n1].")
    first = messages[0]["content"]
    assert first.index("1. Short titles.") < first.index("## What Charie knows")
    assert first.index("## What Charie knows") < first.index("Net sales is [n1].")
    assert messages[1]["content"].endswith("sales.")


def test_inputs_fill_places(prompts_dir):
    prompt = load_prompt("name_chat", prompts_dir)
    messages = build_messages(prompt, {"topic": {"rows": [1, 2]}})
    assert '"rows": [\n    1,\n    2\n  ]' in messages[1]["content"]


def test_missing_input_named(prompts_dir):
    prompt = load_prompt("name_chat", prompts_dir)
    with pytest.raises(AiError, match="Place `topic` has no input."):
        build_messages(prompt, {})


def test_extra_input_named(prompts_dir):
    prompt = load_prompt("name_chat", prompts_dir)
    with pytest.raises(AiError, match="Input `other` has no place in the task."):
        build_messages(prompt, {"topic": "sales", "other": "x"})
