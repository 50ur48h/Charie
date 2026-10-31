"""Default meanings: validation and question topics (P09.4).

A default says what a vague word stands for: `default.sales` names the
tested metric behind "sales", `default.last_week` picks one of two week
definitions, `default.period` picks a supported period expression, and
`default.best` stays unresolved while "best" is ambiguous. Guessed
defaults await owner confirmation; P09.5 turns them into questions.
"""

from charie.shared.knowledge.store import get_entry, list_entries

LAST_WEEK_VALUES = ("last_full_week", "last_7_days")

SUPPORTED_PERIODS = (
    "latest_full_month",
    "latest_full_week",
    "latest_full_quarter",
    "latest_full_year",
)

DEFAULT_KEYS = ("default.sales", "default.last_week", "default.period", "default.best")


def validate_default(word: str, value: str, tested_metrics: set[str]) -> list[str]:
    """Problems with one default; empty means code can trust it."""
    if word == "sales":
        if not value:
            return ["default.sales needs a tested metric."]
        if value not in tested_metrics:
            return [f"{value} is not a tested metric."]
        return []
    if word == "last_week":
        if value in LAST_WEEK_VALUES:
            return []
        return [f"{value} is not a supported week meaning (one of {', '.join(LAST_WEEK_VALUES)})."]
    if word == "period":
        if value in SUPPORTED_PERIODS:
            return []
        return [f"{value} is not a supported period (one of {', '.join(SUPPORTED_PERIODS)})."]
    if word == "best":
        if not value:
            return []
        if value not in tested_metrics:
            return [f"{value} is not a tested metric."]
        return []
    return [f"{word} is not a known default word."]


def tested_metric_keys(session, version_id: int) -> set[str]:
    """Metric keys with no failed check: safe targets for defaults."""
    tested = set()
    for entry in list_entries(session, version_id, kinds=["metric"]):
        details = entry.details if isinstance(entry.details, dict) else {}
        checks = details.get("tests") or []
        usable = checks and all(check.get("passed") is not False for check in checks)
        ran = any(check.get("name") == "runs" and check.get("passed") for check in checks)
        if usable and ran:
            tested.add(entry.key)
    return tested


def _alternatives(word: str, value: str, tested_metrics: set[str]) -> list[str]:
    """Meanings the owner can pick instead of the guess."""
    if word == "sales" or (word == "best" and value):
        return sorted(metric for metric in tested_metrics if metric != value)
    if word == "last_week":
        return [choice for choice in LAST_WEEK_VALUES if choice != value]
    if word == "period":
        return [choice for choice in SUPPORTED_PERIODS if choice != value]
    if word == "best":
        return sorted(tested_metrics)
    return []


def default_topics(session, version_id: int) -> list[dict]:
    """Guessed defaults as owner-question topics, with a safe default each."""
    tested = tested_metric_keys(session, version_id)
    topics = []
    for entry in list_entries(session, version_id, kinds=["default"]):
        if entry.confidence == "confirmed":
            continue
        details = entry.details if isinstance(entry.details, dict) else {}
        word = details.get("word") or ""
        value = details.get("value") or ""
        topics.append(
            {
                "origin": "default",
                "topic": f"What “{word or entry.title}” means",
                "entry_key": entry.key,
                "affects": sorted(details.get("metrics") or []),
                "metric_key": value if value in tested else "",
                "context": {
                    "word": word,
                    "proposed": value,
                    "alternatives": _alternatives(word, value, tested),
                    "safe": value,
                },
            }
        )
    return sorted(topics, key=lambda topic: topic["entry_key"])


def defaults_for(session, version_id: int) -> dict[str, str]:
    """Confirmed or guessed values by default key, for builders (P10.3)."""
    found = {}
    for key in DEFAULT_KEYS:
        entry = get_entry(session, version_id, key)
        if entry is None:
            continue
        details = entry.details if isinstance(entry.details, dict) else {}
        if details.get("value"):
            found[key] = details["value"]
    return found
