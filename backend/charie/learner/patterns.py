"""Value shapes for profiling: `MEGA0926` looks like `AAAA9999` (P07.7)."""

import re

_LETTER = re.compile(r"[A-Za-z]")
_DIGIT = re.compile(r"[0-9]")

#: A shape counts only when this share of values wears it.
PATTERN_SHARE = 0.8


def shape(value: str) -> str:
    """Letters become `A`, digits become `9`; anything else stays."""
    return "".join(
        "A" if _LETTER.fullmatch(char) else "9" if _DIGIT.fullmatch(char) else char
        for char in value
    )


def main_pattern(values: list[str]) -> tuple[str | None, float]:
    """The most common shape and its share, or no shape below 80%."""
    if not values:
        return None, 0.0
    counts: dict[str, int] = {}
    for value in values:
        key = shape(value)
        counts[key] = counts.get(key, 0) + 1
    top, hits = max(counts.items(), key=lambda item: (item[1], item[0]))
    share = hits / len(values)
    if share < PATTERN_SHARE:
        return None, share
    return top, share
