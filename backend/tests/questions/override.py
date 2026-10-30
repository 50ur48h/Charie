"""Change a score after the owner's spot-check; the reason is saved (P06.6)."""

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tests.questions.report import RunReport, ScoredQuestion, points_text, write_report
from tests.questions.run import HIDDEN_REPORTS_DIR, REPORTS_DIR

ALLOWED_POINTS = (Decimal(1), Decimal("0.5"), Decimal(0), Decimal(-1))


class OverrideError(Exception):
    """The override was refused, in the user's own words."""


def _newest_report(folder: Path, set_name: str) -> Path:
    """The latest `.json` report, by file time."""
    files = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise OverrideError(f"No {set_name} report yet.")
    return files[0]


def _read_report(path: Path) -> RunReport:
    """Rebuild the run from its `.json` file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return RunReport(
        set_name=data["set"],
        mode=data["mode"],
        started_at=datetime.fromisoformat(data["started_at"]),
        seconds=data["seconds"],
        results=[
            ScoredQuestion(
                question_id=row["id"],
                kind=row["kind"],
                smoke=row["smoke"],
                points=Decimal(row["points"]),
                outcome=row["outcome"],
                numbers_found=row["numbers_found"],
                numbers_total=row["numbers_total"],
                judge_score=row["judge_score"],
                reason=row["reason"],
                answer_text=row["answer_text"],
                wrong_claims=row["wrong_claims"],
                chat_url=row["chat_url"],
                seconds=row["seconds"],
                cost_usd=Decimal(row["cost_usd"]),
                override_points=(
                    Decimal(row["override_points"]) if row["override_points"] is not None else None
                ),
                override_reason=row.get("override_reason", ""),
            )
            for row in data["rows"]
        ],
        kind=data.get("kind"),
        some=data.get("some", False),
    )


def override_latest(
    folder: Path, set_name: str, question_id: str, points: Decimal, reason: str
) -> str:
    """Set one override in the newest report; the totals use it."""
    if points not in ALLOWED_POINTS:
        raise OverrideError("Points must be 1, 0.5, 0 or -1.")
    path = _newest_report(folder, set_name)
    report = _read_report(path)
    row = next((row for row in report.results if row.question_id == question_id), None)
    if row is None:
        raise OverrideError(f"No question {question_id} in the latest {set_name} report.")
    old = row.override_points if row.override_points is not None else row.points
    updated = [
        ScoredQuestion(
            question_id=item.question_id,
            kind=item.kind,
            smoke=item.smoke,
            points=item.points,
            outcome=item.outcome,
            numbers_found=item.numbers_found,
            numbers_total=item.numbers_total,
            judge_score=item.judge_score,
            reason=item.reason,
            answer_text=item.answer_text,
            wrong_claims=item.wrong_claims,
            chat_url=item.chat_url,
            seconds=item.seconds,
            cost_usd=item.cost_usd,
            override_points=points if item.question_id == question_id else item.override_points,
            override_reason=reason if item.question_id == question_id else item.override_reason,
        )
        for item in report.results
    ]
    path.unlink()
    path.with_suffix(".md").unlink(missing_ok=True)
    write_report(
        RunReport(
            set_name=report.set_name,
            mode=report.mode,
            started_at=report.started_at,
            seconds=report.seconds,
            results=updated,
            kind=report.kind,
            some=report.some,
        ),
        folder,
        datetime.now(UTC),
    )
    total = sum(
        (item.override_points if item.override_points is not None else item.points)
        for item in updated
    )
    best = len(updated)
    percent = (total / best * 100) if best else Decimal(0)
    return (
        f"{question_id}: {points_text(old)} → {points_text(points)}. "
        f"New score: {total} of {best} ({percent:.0f}%)."
    )


def main(argv: list[str] | None = None) -> int:
    """Usage: override --latest public|hidden --id <id> --points 1|0.5|0|-1 --reason <text>."""
    parser = argparse.ArgumentParser(description="Change one score with a saved reason.")
    parser.add_argument("--latest", required=True, choices=["public", "hidden"])
    parser.add_argument("--id", required=True)
    parser.add_argument("--points", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    try:
        points = Decimal(args.points)
    except InvalidOperation:
        print("Points must be 1, 0.5, 0 or -1.")
        return 1
    folder = REPORTS_DIR if args.latest == "public" else HIDDEN_REPORTS_DIR
    try:
        print(override_latest(folder, args.latest, args.id, points, args.reason))
    except OverrideError as err:
        print(err)
        return 1
    except OSError:
        print(f"No {args.latest} report yet.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
