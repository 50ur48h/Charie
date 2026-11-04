"""What form a result should take, decided by the platform (WP13.20)."""

from __future__ import annotations

from dataclasses import dataclass

from charie.agent.charts import MAX_CATEGORIES, MAX_SERIES, Frame, kind_of

__all__ = ["Shape", "shape_of"]


@dataclass(frozen=True, slots=True)
class Shape:
    """The form a result should take, and why — the why being for the trace."""

    mark: str = ""
    x: str = ""
    y: str = ""
    series: str = ""
    reason: str = ""

    @property
    def draws(self) -> bool:
        return bool(self.mark)


def _columns_by_kind(frame: Frame) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {"quantitative": [], "temporal": [], "nominal": []}
    for index, name in enumerate(frame.columns):
        values = [row[index] for row in frame.rows if index < len(row)]
        found[kind_of(values)].append(name)
    return found


def _distinct(frame: Frame, name: str) -> int:
    index = frame.columns.index(name)
    return len({row[index] for row in frame.rows if index < len(row)})


def shape_of(frame: Frame) -> Shape:
    """The form this result should take."""
    if not frame.rows or not frame.columns:
        return Shape(reason="the result has no rows to draw")
    if frame.truncated:
        # `decide` refuses this too.
        return Shape(
            reason="the result was cut off at the row limit, so a chart of it "
            "would look complete while being partial"
        )

    kinds = _columns_by_kind(frame)
    numbers = kinds["quantitative"]
    if not numbers:
        return Shape(reason="nothing in the result is a number to plot")
    if len(frame.rows) == 1 and len(frame.columns) == 1:
        return Shape(reason="a single figure is a sentence, not a picture")

    y = numbers[0]

    for axis, mark in (("temporal", "line"), ("nominal", "bar")):
        candidates = [name for name in kinds[axis] if name != y]
        if not candidates:
            continue
        x = candidates[0]
        if axis == "nominal" and _distinct(frame, x) > MAX_CATEGORIES:
            return Shape(
                reason=f"{x} has more distinct values than a chart has room for",
            )
        # A remaining category splits the marks rather than starting a second answer.
        rest = [
            name
            for name in kinds["nominal"]
            if name not in {x, y} and _distinct(frame, name) <= MAX_SERIES
        ]
        series = rest[0] if rest else ""
        why = f"{'a date' if axis == 'temporal' else 'a category'} against a number"
        if series:
            why += f", split by {series}"
        return Shape(mark=mark, x=x, y=y, series=series, reason=why)

    return Shape(reason="the result has numbers but nothing to plot them against")
