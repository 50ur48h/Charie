"""Masking the values that come back (architecture Part 7.6)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from charie.catalog.browse import Catalog
from charie.connectors.base import ResultFrame
from charie.dal.validator import ColumnRef, Projection

__all__ = ["MaskStyle", "mask_frame", "mask_value", "styles_for"]

MASK_AUTO = "auto"
MASK_FULL = "full"
MASK_EMAIL = "email"
MASK_PHONE = "phone"
MASK_LAST4 = "last4"
MASK_HASH = "hash"

#: What a masked cell says when nothing about its shape is worth keeping.
REDACTED = "***"

#: Enough digits to be a phone number rather than a house number or a year.
_PHONE_DIGITS = 7

MaskStyle = str


@dataclass(frozen=True, slots=True)
class MaskedFrame:
    """A result whose sensitive cells have been replaced, and the record of it."""

    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]
    truncated: bool
    duration_ms: int
    #: Output column names that were masked.
    masked_columns: tuple[str, ...]

    @property
    def row_count(self) -> int:
        return len(self.rows)


def styles_for(catalog: Catalog) -> dict[ColumnRef, MaskStyle]:
    """The mask each masked column asks for, by name."""
    styles: dict[ColumnRef, MaskStyle] = {}
    for table in catalog.tables:
        for column in table.columns:
            if column.policy != "mask":
                continue
            ref = ColumnRef(table.schema_name, table.table_name, column.name)
            styles[ref] = column.mask_type or MASK_AUTO
    return styles


def mask_value(value: object, style: MaskStyle) -> object:
    """One cell. Anything that is not text is redacted rather than reshaped."""
    if value is None:
        return None
    if not isinstance(value, str):
        return REDACTED
    if not value:
        return value

    if style == MASK_AUTO:
        return _mask_auto(value)
    if style == MASK_EMAIL:
        return _mask_email(value)
    if style == MASK_PHONE:
        return _mask_phone(value)
    if style == MASK_LAST4:
        return f"{REDACTED}{value[-4:]}" if len(value) > 4 else REDACTED
    if style == MASK_HASH:
        return f"sha256:{hashlib.sha256(value.encode()).hexdigest()[:12]}"
    return REDACTED


def mask_frame(
    frame: ResultFrame,
    projections: tuple[Projection, ...],
    styles: dict[ColumnRef, MaskStyle],
) -> MaskedFrame:
    """Apply the column policies to a result, by position."""
    if len(projections) != len(frame.columns):
        return _mask_everything(frame)

    sensitive = [
        (index, _style(projection, styles))
        for index, projection in enumerate(projections)
        if projection.sensitive
    ]
    if not sensitive:
        return MaskedFrame(
            columns=frame.columns,
            rows=frame.rows,
            truncated=frame.truncated,
            duration_ms=frame.duration_ms,
            masked_columns=(),
        )

    rows: list[tuple[object, ...]] = []
    for row in frame.rows:
        values = list(row)
        for index, style in sensitive:
            values[index] = mask_value(values[index], style)
        rows.append(tuple(values))

    return MaskedFrame(
        columns=frame.columns,
        rows=tuple(rows),
        truncated=frame.truncated,
        duration_ms=frame.duration_ms,
        masked_columns=tuple(frame.columns[index] for index, _ in sensitive),
    )


def _style(projection: Projection, styles: dict[ColumnRef, MaskStyle]) -> MaskStyle:
    # A derived value — UPPER(email), a concatenation — has no shape left to preserve.
    if projection.source is None:
        return MASK_FULL
    return styles.get(projection.source, MASK_FULL)


def _mask_everything(frame: ResultFrame) -> MaskedFrame:
    return MaskedFrame(
        columns=frame.columns,
        rows=tuple(tuple(REDACTED for _ in row) for row in frame.rows),
        truncated=frame.truncated,
        duration_ms=frame.duration_ms,
        masked_columns=frame.columns,
    )


def _mask_auto(value: str) -> str:
    """Keep the shape the value actually has, rather than one it was declared to."""
    if "@" in value:
        return _mask_email(value)
    if sum(character.isdigit() for character in value) >= _PHONE_DIGITS:
        return _mask_phone(value)
    return REDACTED


def _mask_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator:
        return REDACTED
    name, _, extension = domain.rpartition(".")
    domain_hint = f"{name[:1]}***.{extension}" if name else REDACTED
    return f"{local[:1]}***@{domain_hint}"


def _mask_phone(value: str) -> str:
    digits = [character for character in value if character.isdigit()]
    return f"{REDACTED}{''.join(digits[-4:])}" if len(digits) >= 4 else REDACTED
