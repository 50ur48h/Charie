"""The quote check: word for word, forgiving only spacing and curlies (P10.8)."""

from charie.shared.text.quotes import quote_appears


def test_exact_quote_appears() -> None:
    """The exact sentence is found in its section."""
    assert quote_appears(
        "Net sales means total orders minus refunds.",
        "Net sales means total orders minus refunds. Net sales were $1.2M in 2025.",
    )


def test_line_breaks_are_ignored() -> None:
    """Line breaks and runs of spaces count as one space."""
    assert quote_appears("Use code MEGA0926 at checkout.", "Use code\nMEGA0926   at checkout.")


def test_curly_quotes_match_straight() -> None:
    """Curly punctuation matches its straight form."""
    assert quote_appears(
        'He said "go".',
        "He said \u201cgo\u201d.",
    )


def test_changed_word_fails() -> None:
    """A changed word never matches, even when everything else does."""
    assert not quote_appears(
        "Net sales means gross sales.",
        "Net sales means total orders minus refunds.",
    )
