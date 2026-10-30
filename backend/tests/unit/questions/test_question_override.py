"""Score overrides: the totals use them, the reason is saved (P06.6)."""

import json
import os
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tests.questions import override as override_module
from tests.questions.override import OverrideError, override_latest
from tests.questions.report import RunReport, ScoredQuestion, write_report


def _row(question_id, kind, points, outcome, answer_text="answer text") -> ScoredQuestion:
    return ScoredQuestion(
        question_id=question_id,
        kind=kind,
        smoke=False,
        points=points,
        outcome=outcome,
        numbers_found=1,
        numbers_total=1,
        judge_score=1.0,
        reason="reason",
        answer_text=answer_text,
        seconds=1.0,
    )


def _report() -> RunReport:
    return RunReport(
        set_name="public",
        mode="dry-run",
        started_at=datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC),
        seconds=2.0,
        results=[
            _row("clear-901", "clear", Decimal(1), "correct"),
            _row("why-901", "why", Decimal(-1), "wrong"),
        ],
    )


def test_override_changes_points_and_totals(tmp_path) -> None:
    write_report(_report(), tmp_path, datetime(2026, 10, 30, tzinfo=UTC))
    line = override_latest(tmp_path, "public", "why-901", Decimal("0.5"), "half right")
    assert line == "why-901: −1 → ½. New score: 1.5 of 2 (75%)."
    data = json.loads(sorted(tmp_path.glob("*.json"))[0].read_text(encoding="utf-8"))
    changed = next(row for row in data["rows"] if row["id"] == "why-901")
    assert changed["override_points"] == "0.5"
    assert changed["override_reason"] == "half right"
    markdown = sorted(tmp_path.glob("*.md"))[0].read_text(encoding="utf-8")
    assert "Score: 1.5 of 2 (75%)" in markdown
    assert "why-901: −1 → ½. Reason: half right" in markdown


def test_override_rejects_bad_points(tmp_path) -> None:
    write_report(_report(), tmp_path, datetime(2026, 10, 30, tzinfo=UTC))
    with pytest.raises(OverrideError, match="Points must be 1, 0.5, 0 or -1."):
        override_latest(tmp_path, "public", "why-901", Decimal("2"), "too generous")


def test_override_unknown_id(tmp_path) -> None:
    write_report(_report(), tmp_path, datetime(2026, 10, 30, tzinfo=UTC))
    with pytest.raises(OverrideError, match="No question clear-099 in the latest public report."):
        override_latest(tmp_path, "public", "clear-099", Decimal(1), "not there")


def test_override_hidden_prints_only_ids_and_points(tmp_path, capsys, monkeypatch) -> None:
    hidden = RunReport(
        set_name="hidden",
        mode="dry-run",
        started_at=datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC),
        seconds=1.0,
        results=[_row("h01", "clear", Decimal(1), "correct", answer_text="SECRET words")],
    )
    write_report(hidden, tmp_path, datetime(2026, 10, 30, tzinfo=UTC))
    monkeypatch.setattr(override_module, "HIDDEN_REPORTS_DIR", tmp_path)
    code = override_module.main(
        ["--latest", "hidden", "--id", "h01", "--points", "0.5", "--reason", "partly"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert out == "h01: +1 → ½. New score: 0.5 of 1 (50%).\n"
    assert "SECRET" not in out


def test_override_uses_newest_report(tmp_path) -> None:
    _first_md, first_json = write_report(_report(), tmp_path, datetime(2026, 10, 30, tzinfo=UTC))
    _second_md, second_json = write_report(_report(), tmp_path, datetime(2026, 10, 30, tzinfo=UTC))
    old_time = time.time() - 100
    os.utime(first_json, (old_time, old_time))
    line = override_latest(tmp_path, "public", "why-901", Decimal(0), "nope")
    assert line.startswith("why-901: −1 → 0.")
    data = json.loads(second_json.read_text(encoding="utf-8"))
    assert next(row for row in data["rows"] if row["id"] == "why-901")["override_points"] == "0"
    untouched = json.loads(first_json.read_text(encoding="utf-8"))
    assert (
        next(row for row in untouched["rows"] if row["id"] == "why-901")["override_points"] is None
    )


def test_override_no_report_yet(tmp_path) -> None:
    with pytest.raises(OverrideError, match="No public report yet."):
        override_latest(tmp_path, "public", "clear-901", Decimal(1), "nothing there")
