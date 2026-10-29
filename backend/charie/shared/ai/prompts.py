"""Prompt files: stable parts first for caching, task data last (03)."""

import json
from pathlib import Path

from charie.shared.ai.errors import AiError

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

SECTIONS = ("## Rules", "## Examples", "## Task")


def load_prompt(job: str, prompts_dir: Path | None = None) -> dict[str, str]:
    """The job's 3 prompt sections, in order; names what's wrong or missing."""
    folder = prompts_dir or PROMPTS_DIR
    path = folder / f"{job}.md"
    if not path.exists():
        raise AiError("missing_prompt", f"There's no prompt file for job `{job}`: {path}.")
    parts = split_sections(path.read_text(encoding="utf-8"))
    for section in SECTIONS:
        if section not in parts:
            raise AiError(
                "bad_prompt",
                f"The prompt file for job `{job}` is missing section `{section}`.",
            )
    return {section: parts[section] for section in SECTIONS}


def split_sections(text: str) -> dict[str, str]:
    """Split a prompt file on its `## ` headings."""
    parts: dict[str, str] = {}
    current: str | None = None
    for line in text.split("\n"):
        if line.startswith("## "):
            current = line.strip()
            parts[current] = ""
        elif current is not None:
            parts[current] += line + "\n"
    return {section: body.strip() for section, body in parts.items()}


def build_messages(
    prompt: dict[str, str],
    inputs: dict[str, object],
    knowledge_summary: str | None = None,
) -> list[dict[str, str]]:
    """System message (stable parts, then knowledge), then the filled task."""
    system = prompt["## Rules"].strip() + "\n\n" + prompt["## Examples"].strip()
    if knowledge_summary:
        system += "\n\n## What Charie knows\n" + knowledge_summary.strip()
    task = prompt["## Task"]
    for name, value in inputs.items():
        place = "{{" + name + "}}"
        if place not in task:
            raise AiError("bad_prompt", f"Input `{name}` has no place in the task.")
        task = task.replace(place, render_value(value))
    for place in _places(task):
        raise AiError("bad_prompt", f"Place `{place}` has no input.")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": task.strip()},
    ]


def render_value(value: object) -> str:
    """Text as-is; anything else as indented JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, sort_keys=True)


def _places(task: str) -> list[str]:
    import re

    return sorted(set(re.findall(r"\{\{(\w+)\}\}", task)))
