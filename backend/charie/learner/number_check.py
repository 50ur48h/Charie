"""Numbers the AI typed that the notes never said (P07.5).

The AI never types numbers: a title or meaning with a number that isn't
in the quoted notes falls back to the quote itself.
"""

import re

_NUMBER = re.compile(r"[+-]?\$?\d[\d,]*(?:\.\d+)?(?:-\d[\d,]*(?:\.\d+)?)?%?")


def find_numbers(text: str) -> list[str]:
    """Number-like tokens in reading order, duplicates kept apart."""
    seen: list[str] = []
    for match in _NUMBER.finditer(text or ""):
        token = match.group(0).strip(".,")
        if token and token not in seen:
            seen.append(token)
    return seen


def find_new_numbers(texts: list[str], source: str) -> list[str]:
    """Numbers in `texts` whose complete token the source never uses.

    Tokens compare whole: `10%` is new next to `110%`, `-5` is new next
    to `5`, and `1,000` stays different from `1000`. The sign, `$`,
    range and `%` are part of the token; the note's own numbers match
    exactly as written.
    """
    source_tokens = set(find_numbers(source or ""))
    return [token for text in texts for token in find_numbers(text) if token not in source_tokens]
