"""Quote checks: a fact's quote must really appear in its section (P08.6).

Comparison ignores whitespace runs and curly punctuation (the P10.8
rule); anything else, including a changed word, refuses to match. The
section text is data: this check runs before any AI comparison.
"""

import re
import unicodedata

_WS_RUN = re.compile(r"\s+")

_CURLY = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        "…": "...",
    }
)


def normalize_text(text: str) -> str:
    """Fold compatibility characters, curly punctuation and whitespace runs."""
    folded = unicodedata.normalize("NFKC", text or "")
    return _WS_RUN.sub(" ", folded.translate(_CURLY)).strip()


def quote_appears(quote: str, text: str) -> bool:
    """The quote appears word for word; a changed word never matches."""
    folded = normalize_text(quote)
    return bool(folded) and folded in normalize_text(text)
