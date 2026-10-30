"""Test reports: one Markdown and one JSON file per run (08)."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class ScoredQuestion:
    """A question with its score, for the report tables."""

    question_id: str
    kind: str
    smoke: bool
    points: Decimal
    outcome: str
    numbers_found: int
    numbers_total: int
    judge_score: float | None
    reason: str
    answer_text: str
    wrong_claims: list[str] = field(default_factory=list)
    chat_url: str = ""
    seconds: float = 0.0
    cost_usd: Decimal = Decimal("0")
    override_points: Decimal | None = None
    override_reason: str = ""


@dataclass(frozen=True)
class RunReport:
    """A whole run: set, mode, and one row per question."""

    set_name: str
    mode: str
    started_at: datetime
    seconds: float
    results: list[ScoredQuestion] = field(default_factory=list)
    kind: str | None = None
    some: bool = False


def _best(report: RunReport) -> int:
    """Best possible total: +1 per question."""
    return len(report.results)


def _points(report: RunReport) -> Decimal:
    """Total points (P06.6 overrides already applied in the rows)."""
    return sum((row.points for row in report.results), Decimal(0))


def _by_kind(report: RunReport) -> dict[str, list[ScoredQuestion]]:
    """Rows grouped by kind, kinds in alphabetical order."""
    groups: dict[str, list[ScoredQuestion]] = {}
    for row in report.results:
        groups.setdefault(row.kind, []).append(row)
    return dict(sorted(groups.items()))


def _money(value: Decimal) -> str:
    return f"${value:.2f}"


def report_markdown(report: RunReport) -> str:
    """The human report: header, summary, by kind, every question, gaps."""
    points = _points(report)
    best = _best(report)
    percent = (points / best * 100) if best else Decimal(0)
    cost = sum((row.cost_usd for row in report.results), Decimal(0))
    kinds = _by_kind(report)
    clear_wrong = sum(1 for row in kinds.get("clear", []) if row.outcome == "wrong")
    lines = [
        f"# Test report: {report.set_name} ({report.mode})",
        "",
        f"Date and time: {report.started_at.isoformat(timespec='seconds')}",
        "",
        "## Summary",
        "",
        f"Score: {points} of {best} ({percent:.0f}%)",
        f"Clear questions wrong: {clear_wrong}",
        f"Cost: {_money(cost)}",
        f"Time: {report.seconds:.1f}s",
        "",
        "## Score by kind",
        "",
        "| kind | questions | correct | partly | don't know | wrong | errors "
        "| points | best | % | avg time | cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for kind, rows in kinds.items():
        kind_points = sum((row.points for row in rows), Decimal(0))
        kind_best = len(rows)
        kind_percent = (kind_points / kind_best * 100) if kind_best else Decimal(0)
        avg_time = sum(row.seconds for row in rows) / len(rows) if rows else 0.0
        kind_cost = sum((row.cost_usd for row in rows), Decimal(0))
        lines.append(
            f"| {kind} | {len(rows)} | "
            f"{sum(1 for row in rows if row.outcome == 'correct')} | "
            f"{sum(1 for row in rows if row.outcome == 'partly')} | "
            f"{sum(1 for row in rows if row.outcome == 'dont_know')} | "
            f"{sum(1 for row in rows if row.outcome == 'wrong')} | "
            f"{sum(1 for row in rows if row.outcome == 'error')} | "
            f"{kind_points} | {kind_best} | {kind_percent:.0f}% | "
            f"{avg_time:.1f}s | {_money(kind_cost)} |"
        )
    lines += ["", "## Every question", ""]
    lines += ["| id | kind | smoke | points | numbers | judge | time | cost |"]
    lines += ["|---|---|---|---|---|---|---|---|"]
    for row in report.results:
        judge = f"{row.judge_score:.2f}" if row.judge_score is not None else "-"
        lines.append(
            f"| {row.question_id} | {row.kind} | {'yes' if row.smoke else 'no'} | "
            f"{row.points} | {row.numbers_found} of {row.numbers_total} | "
            f"{judge} | {row.seconds:.1f}s | {_money(row.cost_usd)} |"
        )
    lines += ["", "## Not fully correct", ""]
    gaps = [row for row in report.results if row.outcome != "correct"]
    if not gaps:
        lines.append("Everything was correct.")
    for row in gaps:
        claims = "; ".join(row.wrong_claims) if row.wrong_claims else "-"
        link = row.chat_url if row.chat_url else "fake answer, no link"
        lines += [
            f"### {row.question_id} ({row.outcome}, {row.points})",
            "",
            f"Reason: {row.reason or '-'}",
            f"Wrong claims: {claims}",
            f"Link: {link}",
            "",
        ]
    lines += ["## Errors", ""]
    errors = [row for row in report.results if row.outcome == "error"]
    if not errors:
        lines.append("No errors.")
    for row in errors:
        lines.append(f"- {row.question_id}: {row.reason or '-'}")
    lines += ["", "## Spot-check", "", "Not checked yet (P06.6).", ""]
    return "\n".join(lines)


def report_json(report: RunReport) -> str:
    """The machine report: every row with its full score."""
    return json.dumps(
        {
            "set": report.set_name,
            "mode": report.mode,
            "started_at": report.started_at.isoformat(timespec="seconds"),
            "seconds": report.seconds,
            "score": str(_points(report)),
            "best": _best(report),
            "rows": [
                {
                    "id": row.question_id,
                    "kind": row.kind,
                    "smoke": row.smoke,
                    "points": str(row.points),
                    "outcome": row.outcome,
                    "numbers_found": row.numbers_found,
                    "numbers_total": row.numbers_total,
                    "judge_score": row.judge_score,
                    "reason": row.reason,
                    "answer_text": row.answer_text,
                    "wrong_claims": row.wrong_claims,
                    "chat_url": row.chat_url,
                    "seconds": row.seconds,
                    "cost_usd": str(row.cost_usd),
                    "override_points": (
                        str(row.override_points) if row.override_points is not None else None
                    ),
                    "override_reason": row.override_reason,
                }
                for row in report.results
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _report_stem(report: RunReport) -> str:
    """`<YYYY-MM-DD>-<set>[-<kind>][-some][-dry-run]`."""
    parts = [report.started_at.strftime("%Y-%m-%d"), report.set_name]
    if report.kind:
        parts.append(report.kind)
    if report.some:
        parts.append("some")
    if report.mode == "dry-run":
        parts.append("dry-run")
    return "-".join(parts)


def write_report(report: RunReport, folder: str | Path, now: datetime) -> tuple[Path, Path]:
    """Write `<stem>.md` and `<stem>.json`; add `-2`, `-3`, never overwrite."""
    del now  # The name uses the run's start date, not the write time.
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stem = _report_stem(report)
    suffix = ""
    trial = 2
    while (folder / f"{stem}{suffix}.md").exists():
        suffix = f"-{trial}"
        trial += 1
    markdown_path = folder / f"{stem}{suffix}.md"
    json_path = folder / f"{stem}{suffix}.json"
    markdown_path.write_text(report_markdown(report) + "\n", encoding="utf-8")
    json_path.write_text(report_json(report) + "\n", encoding="utf-8")
    return markdown_path, json_path
