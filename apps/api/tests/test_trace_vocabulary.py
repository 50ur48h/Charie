"""Every event the database will store has a word a person can read."""

from __future__ import annotations

import re
from pathlib import Path

from charie.db.models import EVENT_TYPES

TRACE = Path(__file__).resolve().parents[2] / "web" / "src" / "components" / "screens" / "trace.tsx"

#: The record's entries sit at exactly one indent level.
END_OF_RECORD = "\n};"
ENTRY = re.compile(r"^  ([a-z_]+):", re.M)


def step_words() -> set[str]:
    """The keys of `STEP_SENTENCES`, read out of the component that renders them."""
    source = TRACE.read_text(encoding="utf-8")
    block = source.split("const STEP_SENTENCES", 1)[1].split(END_OF_RECORD, 1)[0]
    return set(ENTRY.findall(block))


def test_every_event_type_has_a_word_for_a_person() -> None:
    """A type the database accepts but the screen cannot name is a leak."""
    assert TRACE.exists(), f"{TRACE} not found — did the component move?"

    missing = sorted(set(EVENT_TYPES) - step_words())

    assert missing == [], (
        "these event types will render as raw machine names: "
        f"{missing}. Add a sentence to STEP_SENTENCES in {TRACE.name}."
    )


def test_the_vocabulary_does_not_name_events_that_cannot_happen() -> None:
    """The other direction, which is a smaller problem and still a wrong record."""
    unknown = sorted(step_words() - set(EVENT_TYPES))

    assert unknown == [], (
        f"STEP_SENTENCES names events the schema does not allow: {unknown}. "
        "Either the CHECK constraint lost a type or the vocabulary invented one."
    )
