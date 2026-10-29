"""Number formatting: one set of rules for every number a person sees."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

Number = Decimal | int | str

MINUS = "\u2212"
EN_DASH = "\u2013"
CURRENCIES = {"USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "INR": "\u20b9"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UNITS = (("B", Decimal(10**9)), ("M", Decimal(10**6)), ("K", Decimal(10**3)))


def _to_decimal(value: Number) -> Decimal:
    if isinstance(value, float):
        raise TypeError("Use Decimal or str for numbers, not float.")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            raise ValueError(f"{value!r} is not a number.") from None
    raise TypeError("Use Decimal or str for numbers, not float.")


def _round(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def _sign(value: Decimal) -> str:
    return MINUS if value < 0 else ""


def _drop_zeros(text: str) -> str:
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".")


def _scaled(scaled: Decimal, suffix: str, index: int) -> tuple[str, str]:
    """3 significant digits, rolling over (999,999 -> 1M, never 1000K)."""
    places = 0 if scaled >= 100 else 1 if scaled >= 10 else 2
    rounded = _round(scaled, places)
    if rounded >= 1000 and index > 0:
        return _scaled(scaled / 1000, UNITS[index - 1][0], index - 1)
    return _drop_zeros(f"{rounded:f}"), suffix


def _short_scaled(abs_value: Decimal) -> tuple[str, str]:
    for index, (suffix, size) in enumerate(UNITS):
        if abs_value >= size:
            return _scaled(abs_value / size, suffix, index)
    return _drop_zeros(f"{_round(abs_value, 2):f}"), ""


def format_money(value: Number, currency: str = "USD", style: str = "short") -> str:
    amount = _to_decimal(value)
    symbol = CURRENCIES.get(currency, f"{currency} ")
    if 0 < abs(amount) < Decimal("0.01"):
        return f"{_sign(amount)}<{symbol}0.01"
    if abs(amount) < 1000:
        return f"{_sign(amount)}{symbol}{_round(abs(amount), 2):.2f}"
    if style == "full":
        return f"{_sign(amount)}{symbol}{_round(abs(amount), 0):,.0f}"
    scaled, suffix = _short_scaled(abs(amount))
    return f"{_sign(amount)}{symbol}{scaled}{suffix}"


def format_count(value: Number, style: str = "short") -> str:
    amount = _to_decimal(value)
    whole = _round(abs(amount), 0)
    if style == "short" and whole >= 10000:
        scaled, suffix = _short_scaled(whole)
        return f"{_sign(amount)}{scaled}{suffix}"
    return f"{_sign(amount)}{whole:,.0f}"


def format_percent(value: Number) -> str:
    amount = _to_decimal(value)
    return f"{_sign(amount)}{_drop_zeros(f'{_round(abs(amount), 1):.1f}')}%"


def format_change(value: Number, unit: str, currency: str = "USD", style: str = "short") -> str:
    if unit not in ("money", "count", "percent"):
        raise ValueError(f'Unknown unit "{unit}". Use money, count or percent.')
    amount = _to_decimal(value)
    if amount == 0:
        return {"money": format_money(0, currency, style), "count": "0", "percent": "0%"}[unit]
    if unit == "money":
        return f"{'+' if amount > 0 else MINUS}{format_money(abs(amount), currency, style)}"
    if unit == "count":
        return f"{'+' if amount > 0 else MINUS}{format_count(abs(amount), style)}"
    if unit == "percent":
        return f"{'+' if amount > 0 else MINUS}{format_percent(abs(amount))}"
    raise ValueError(f'Unknown unit "{unit}". Use money, count or percent.')


def format_ratio(value: Number) -> str:
    amount = _to_decimal(value)
    return f"{_sign(amount)}{_round(abs(amount), 2):.2f}"


def _day(text: str) -> datetime:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{text!r} is not a day like 2025-12-31.") from None


def format_date(day: str) -> str:
    date = _day(day)
    return f"{date.day} {MONTHS[date.month - 1]} {date.year}"


def format_period(start: str, end: str) -> str:
    first, last = _day(start), _day(end)
    if first == last:
        return format_date(start)
    if first.year == last.year and first.month == last.month:
        return f"{first.day}{EN_DASH}{last.day} {MONTHS[last.month - 1]} {last.year}"
    if first.year == last.year:
        return (
            f"{first.day} {MONTHS[first.month - 1]}"
            f" {EN_DASH} {last.day} {MONTHS[last.month - 1]} {last.year}"
        )
    return f"{format_date(start)} {EN_DASH} {format_date(end)}"
