"""The practice notes sort into the expected rules (laptop only, P07.5).

Run once with `AI_REPLAY=record` (about $0.10) after reading the printed
list: if it matches "What we expect" in the plan, the replay is saved and
later runs pass with `AI_REPLAY=replay` for $0.
"""

from pathlib import Path

import pytest

from charie.learner.steps.base import StepContext
from charie.learner.steps.owner_notes import run_job
from charie.shared.jobs.registry import JobInfo
from charie.shared.knowledge import store, versions
from charie.shared.tables.learning import LearningRun
from charie.shared.tables.sources import OwnerNote

NOTES_PATH = Path(__file__).resolve().parents[2] / "data" / "practice_owner_notes.md"


def _fold(text: str) -> str:
    """Lowercase without whitespace: quotes match loosely."""
    return "".join(text.split()).lower()


@pytest.mark.live_ai
def test_practice_notes_sort_as_expected(db_session) -> None:
    text = NOTES_PATH.read_text(encoding="utf-8")
    note = OwnerNote(text_=text)
    db_session.add(note)
    version_id = versions.get_or_create_draft(db_session, "first_learning").id
    run = LearningRun(kind="first", status="running", step="owner_notes", version_id=version_id)
    db_session.add(run)
    db_session.commit()

    said: list = []
    ctx = StepContext(
        session=db_session,
        run_id=run.id,
        version_id=version_id,
        source=None,
        connector=None,
        strict_mode=False,
        settings={},
        say=lambda kind, message, details=None: said.append((kind, message)),
    )
    run_job(
        JobInfo(
            id=1,
            kind="sort_owner_notes",
            payload={"owner_notes_id": note.id, "step": "owner_notes"},
            run_id=run.id,
            attempts=1,
        ),
        ctx,
    )
    entries = store.list_entries(db_session, version_id)
    rules = [entry for entry in entries if entry.kind == "rule"]
    styles = [entry for entry in entries if entry.kind == "style"]
    hints = [entry for entry in entries if entry.kind not in ("rule", "style")]

    print("\n--- sorted practice notes ---")
    for entry in entries:
        print(f"[{entry.kind}] {entry.title} -- {entry.meaning}")
    print(f"--- {len(rules)} rules, {len(styles)} styles, {len(hints)} hints ---")

    folded_notes = _fold(text)
    for entry in entries:
        quotes = [source.get("quote", "") for source in entry.sources]
        assert quotes and all(_fold(quote) in folded_notes for quote in quotes), entry.key

    by_type = {entry.details.get("rule_type") for entry in rules}
    assert "currency" in by_type
    assert by_type.isdisjoint({"never_use_table", "always_filter", "exclude_values"})
    profit = [
        entry
        for entry in rules
        if entry.details.get("rule_type") == "required_note"
        and any(
            "v_monthly_outlet_profit_estimate" in table
            for table in entry.details.get("applies_to_tables", [])
        )
    ]
    assert len(profit) == 1
    assert "profit" in profit[0].meaning.lower()

    assert len(styles) >= 3
    style_text = " ".join(entry.title + " " + entry.meaning for entry in styles).lower()
    assert "outlet" in style_text and "unit" in style_text

    assert len(hints) >= 8
    hint_text = " ".join(entry.title + " " + entry.meaning for entry in hints).lower()
    assert "join" in hint_text and "waste" in hint_text
