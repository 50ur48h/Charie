"""Code does all the math (06): totals, changes, shares, ranks and trends.

Every number stays exact until it is shown: inputs are `Decimal`, `int` or
`str` (a `float` is refused), sums stay exact in DuckDB `DECIMAL`, and
divisions use Python's `Decimal`. Nothing is rounded here.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import duckdb

from charie.shared.text.numbers import format_date

_USE_DECIMAL = "Use Decimal or str for numbers, not float."


class CalcError(Exception):
    """The math couldn't be done; the message is plain English."""


def _to_decimal(value: object, what: str = "value") -> Decimal | None:
    """A number as an exact `Decimal`; empty stays empty, float is refused."""
    if value is None or value == "":
        return None
    if isinstance(value, float):
        raise CalcError(_USE_DECIMAL)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise CalcError(f"`{value}` isn't a number.") from None
    raise CalcError(f"Can't do math on `{what}`: use Decimal, int or str.")


def _check_currency(first: str | None, second: str | None) -> None:
    """Two different currencies never mix (percentages carry no currency)."""
    if first is not None and second is not None and first != second:
        raise CalcError(
            f"Can't add or compare amounts in different currencies (`{first}` and `{second}`)."
        )


def _quote(name: str) -> str:
    """A column name as a quoted identifier."""
    return '"' + name.replace('"', '""') + '"'


class ResultTable:
    """Query rows in an in-memory DuckDB table, one connection per table."""

    def __init__(self, columns: list[str], rows: list[list]) -> None:
        for row in rows:
            if len(row) != len(columns):
                raise CalcError("Each row must have one value per column.")
        self._columns = list(columns)
        self._rows = [list(row) for row in rows]
        self._shapes = self._column_shapes()
        self._connection = duckdb.connect()
        try:
            parts = ["__i INTEGER"]
            for position, column in enumerate(self._columns):
                shape = self._shapes[position]
                parts.append(
                    f"{_quote(column)} DECIMAL({shape[0]}, {shape[1]})"
                    if shape is not None
                    else f"{_quote(column)} VARCHAR"
                )
            self._connection.execute(f"CREATE TABLE rows ({', '.join(parts)})")
            placeholders = ", ".join(["?"] * (len(columns) + 1))
            values = []
            for index, row in enumerate(self._rows):
                converted = [index]
                for position in range(len(columns)):
                    value = row[position]
                    converted.append(
                        _to_decimal(value) if self._shapes[position] is not None else value
                    )
                values.append(converted)
            if values:
                self._connection.executemany(f"INSERT INTO rows VALUES ({placeholders})", values)
        except Exception:
            self._connection.close()
            raise

    def _column_shapes(self) -> list[tuple[int, int] | None]:
        """`(precision, scale)` per numeric column; None where text lives."""
        shapes: list[tuple[int, int] | None] = []
        for position in range(len(self._columns)):
            column = [row[position] for row in self._rows]
            if any(isinstance(value, float) for value in column):
                raise CalcError(_USE_DECIMAL)
            try:
                decimals = [_to_decimal(value) for value in column]
            except CalcError:
                shapes.append(None)
                continue
            int_digits = 1
            scale = 0
            for value in decimals:
                if value is None:
                    continue
                int_digits = max(int_digits, value.adjusted() + 1)
                scale = max(scale, max(0, -value.as_tuple().exponent))
            precision = min(38, int_digits + scale)
            shapes.append((precision, min(scale, precision - int_digits)))
        return shapes

    def close(self) -> None:
        """Give the connection back."""
        self._connection.close()

    def __enter__(self) -> "ResultTable":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _column(self, column: str) -> int:
        """The position of a column, or a plain refusal."""
        if column not in self._columns:
            raise CalcError(f"There is no column called `{column}`.")
        return self._columns.index(column)

    def total(self, column: str) -> Decimal | None:
        """The sum, skipping empty values (like SQL SUM); none gives None."""
        position = self._column(column)
        if self._shapes[position] is None:
            raise CalcError(f"Can't total `{column}`: it holds text, not numbers.")
        return self._connection.execute(f"SELECT SUM({_quote(column)}) FROM rows").fetchone()[0]

    def rows_sorted(self, column: str, descending: bool = True) -> list[list]:
        """The rows ordered by one column."""
        self._column(column)
        order = "DESC" if descending else "ASC"
        found = self._connection.execute(
            f"SELECT __i FROM rows ORDER BY {_quote(column)} {order}"
        ).fetchall()
        return [self._rows[index[0]] for index in found]

    def rank(self, column: str, descending: bool = True) -> list[tuple[int, list]]:
        """Standard competition ranking (1, 2, 2, 4) with each row."""
        self._column(column)
        order = "DESC" if descending else "ASC"
        found = self._connection.execute(
            f"SELECT RANK() OVER (ORDER BY {_quote(column)} {order}), __i FROM rows"
        ).fetchall()
        return [(position, self._rows[index]) for position, index in found]


def difference(
    new: object,
    old: object,
    currency_new: str | None = None,
    currency_old: str | None = None,
) -> Decimal | None:
    """`new − old` exactly; missing values give None, mixed currencies refuse."""
    _check_currency(currency_new, currency_old)
    first, second = _to_decimal(new, "new"), _to_decimal(old, "old")
    if first is None or second is None:
        return None
    return first - second


def percent_change(
    new: object,
    old: object,
    currency_new: str | None = None,
    currency_old: str | None = None,
) -> Decimal | None:
    """`(new − old) ÷ old × 100` in percent; no change from zero gives None."""
    _check_currency(currency_new, currency_old)
    first, second = _to_decimal(new, "new"), _to_decimal(old, "old")
    if first is None or second is None:
        return None
    if second == 0:
        return None
    return (first - second) / second * 100


def share(
    part: object,
    whole: object,
    currency_new: str | None = None,
    currency_old: str | None = None,
) -> Decimal | None:
    """`part ÷ whole × 100` in percent; nothing of nothing gives None."""
    _check_currency(currency_new, currency_old)
    first, second = _to_decimal(part, "part"), _to_decimal(whole, "whole")
    if first is None or second is None:
        return None
    if second == 0:
        return None
    return first / second * 100


@dataclass
class Trend:
    """Which way a series moves, and whether the move is real."""

    direction: str
    steps: int
    steps_that_way: int
    share_that_way: Decimal
    is_real: bool


def trend(values: list) -> Trend:
    """The direction and strength of a series; fewer than 3 points is no trend."""
    numbers = [value for value in (_to_decimal(item) for item in values) if value is not None]
    if len(numbers) < 3:
        return Trend(
            direction="flat",
            steps=max(0, len(numbers) - 1),
            steps_that_way=0,
            share_that_way=Decimal(0),
            is_real=False,
        )
    first, last = numbers[0], numbers[-1]
    direction = "up" if last > first else "down" if last < first else "flat"
    steps = len(numbers) - 1
    pairs = list(zip(numbers, numbers[1:], strict=False))
    if direction == "up":
        that_way = sum(1 for before, after in pairs if after > before)
    elif direction == "down":
        that_way = sum(1 for before, after in pairs if after < before)
    else:
        that_way = sum(1 for before, after in pairs if after == before)
    share = Decimal(that_way) / Decimal(steps)
    return Trend(
        direction=direction,
        steps=steps,
        steps_that_way=that_way,
        share_that_way=share,
        is_real=direction != "flat" and share >= Decimal(2) / Decimal(3),
    )


@dataclass
class PeriodStatus:
    """Whether a period is complete, and the note when it isn't."""

    status: str
    note: str


def _ordinal(day: int) -> str:
    """1st, 2nd, 3rd, 4th … 11th, 12th, 13th … 21st, 22nd, 23rd … 31st."""
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def period_status(
    start: date, end: date, data_through: date, last_day_complete: bool = True
) -> PeriodStatus:
    """Is the period complete, partial, or beyond the data? (06, number check 5)."""
    if end < data_through or (end == data_through and last_day_complete):
        return PeriodStatus(status="complete", note="")
    if start > data_through:
        return PeriodStatus(
            status="no_data",
            note="There's no data for this period yet. The data only goes up to "
            f"`{format_date(data_through.isoformat())}`.",
        )
    last_day = calendar.monthrange(start.year, start.month)[1]
    if start.day == 1 and (end.year, end.month, end.day) == (start.year, start.month, last_day):
        return PeriodStatus(
            status="partial",
            note=f"{data_through.strftime('%B')} has data up to the "
            f"{_ordinal(data_through.day)} only.",
        )
    return PeriodStatus(
        status="partial",
        note=f"This period has data up to `{format_date(data_through.isoformat())}` only.",
    )
