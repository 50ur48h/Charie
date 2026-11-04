"""Which rows are observed and which are modelled (D-053, D-058, B-157)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

__all__ = [
    "MODES",
    "PROVENANCE_COLUMN",
    "caveat",
    "modes_of",
    "rank_of",
    "reorder",
]

#: The column a customer uses to say how a row came to exist.
PROVENANCE_COLUMN = "source_mode"

#: Worst to best. A table is judged by its weakest mode.
MODES: tuple[str, ...] = ("synthetic", "derived", "real")

#: How a mode reads to somebody who did not write the contract.
_PLAIN: Mapping[str, str] = {
    "synthetic": "modelled scenario data rather than observed records",
    "derived": "estimates computed from observed records rather than observed records",
}


def rank_of(modes: Sequence[str]) -> int:
    """Where a table sits, by its weakest mode."""
    known = [mode for mode in modes if mode in MODES]
    return min(MODES.index(mode) for mode in known) if known else len(MODES) - 1


def modes_of(
    columns: Sequence[tuple[str, Sequence[Mapping[str, object]] | None]],
) -> tuple[str, ...]:
    """The modes measured on one table, over ``(column_name, top_values)``."""
    for name, top_values in columns:
        if name.lower() != PROVENANCE_COLUMN or not top_values:
            continue
        found = [str(entry.get("value", "")) for entry in top_values]
        return tuple(mode for mode in MODES if mode in found)
    return ()


def reorder[T](
    cards: Sequence[T],
    *,
    modes: Callable[[T], Sequence[str]],
    answers_questions: Callable[[T], bool],
) -> tuple[T, ...]:
    """Observed data first, among the cards that could each answer."""
    positions = [index for index, card in enumerate(cards) if answers_questions(card)]
    if len(positions) < 2:
        return tuple(cards)
    ordered = sorted(
        (cards[index] for index in positions),
        key=lambda card: -rank_of(modes(card)),
    )
    out = list(cards)
    for index, card in zip(positions, ordered, strict=True):
        out[index] = card
    return tuple(out)


def caveat(read: Mapping[str, Sequence[str]]) -> str:
    """What to say when an answer rests on rows that were not observed."""
    modelled = {
        table: rank_of(modes)
        for table, modes in read.items()
        if modes and rank_of(modes) < len(MODES) - 1
    }
    if not modelled:
        return ""
    worst = MODES[min(modelled.values())]
    names = ", ".join(sorted(modelled))
    plural = "table" if len(modelled) == 1 else "tables"
    return (
        f"This answer reads {plural} the database labels as {worst}: {names}. "
        f"That means {_PLAIN.get(worst, 'not observed records')}, so the figures "
        f"describe what was modelled rather than what was measured."
    )
