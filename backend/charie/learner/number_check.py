"""Numbers the AI typed that the notes never said (P07.5).

The AI never types numbers: a title or meaning with a number that isn't
in the quoted notes falls back to the quote itself.
"""

import re

_NUMBER = re.compile(r"[+-]?\$?\d[\d,]*(?:\.\d+)?(?:-\d[\d,]*(?:\.\d+)?)?%?")


def _fold(text: str) -> str:
    """Lowercase without whitespace: quotes match loosely."""
    return re.sub(r"\s+", "", text.lower())


def find_numbers(text: str) -> list[str]:
    """Number-like tokens in reading order, duplicates kept apart."""
    seen: list[str] = []
    for match in _NUMBER.finditer(text or ""):
        token = match.group(0).strip(".,")
        if token and token not in seen:
            seen.append(token)
    return seen


def find_new_numbers(texts: list[str], source: str) -> list[str]:
    """Numbers in `texts` that `source` doesn't contain (folded)."""
    folded = _fold(source or "")
    return [token for text in texts for token in find_numbers(text) if _fold(token) not in folded]
