"""Labels in AI text: find them, fill them, catch stray digits (P10.4).

The AI never types numbers: text carries labels like `[n1]`, and code
fills in the real values. Anything with a digit that isn't a label or a
known word (like `MEGA0926`) is a problem the checks catch.
"""

import re

#: A label in AI text: `[n1]`, `[t2]`, `[p1]`, `[q3]`.
LABEL_RE = r"\[([ntpq]\d+)\]"

_LABEL = re.compile(LABEL_RE)
_TOKEN = re.compile(r"[A-Za-z0-9%][^\s]*[A-Za-z0-9%]|[A-Za-z0-9%]")
_STRIP = ".,;:!?()\"'"


def labels_in(text: str) -> list[str]:
    """Every label in the text, in order (`n1`, not `[n1]`)."""
    return _LABEL.findall(text)


def fill_labels(text: str, values: dict[str, str]) -> str:
    """Replace each known label with its value; unknown ones stay."""

    def _fill(match: re.Match[str]) -> str:
        return values.get(match.group(1), match.group(0))

    return _LABEL.sub(_fill, text)


def mixed_tokens(texts: list[str]) -> list[str]:
    """Words with both letters and digits, like `MEGA0926`."""
    found: list[str] = []
    for text in texts:
        for token in _TOKEN.findall(text):
            word = token.strip(_STRIP)
            if (
                word not in found
                and any(char.isalpha() for char in word)
                and any(char.isdigit() for char in word)
            ):
                found.append(word)
    return found


def stray_digits(text: str, allowed: list[str]) -> list[str]:
    """Digit words outside labels, minus the known ones.

    Labels are taken out first, so `[p1]` never counts. A bare number
    (`42`) always counts, even when listed as known; a mixed word
    (`MEGA0926`) counts unless it is in `allowed`.
    """
    bare = _LABEL.sub(" ", text)
    stray: list[str] = []
    for token in _TOKEN.findall(bare):
        word = token.strip(_STRIP)
        if not any(char.isdigit() for char in word):
            continue
        if any(char.isalpha() for char in word) and word in allowed:
            continue
        if word not in stray:
            stray.append(word)
    return stray
