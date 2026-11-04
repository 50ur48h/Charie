"""What comes back, and what is left of it (architecture Part 7.6)."""

from __future__ import annotations

import pytest
from catalog_fixture import build_catalog

from charie.connectors.base import ResultFrame
from charie.dal.masking import (
    MASK_HASH,
    MASK_LAST4,
    REDACTED,
    mask_frame,
    mask_value,
    styles_for,
)
from charie.dal.policy import SourcePolicy
from charie.dal.validator import validate

PLANTED = "ada@lovelace.example.com"


def frame(columns: tuple[str, ...], *rows: tuple[object, ...]) -> ResultFrame:
    return ResultFrame(columns=columns, rows=rows, truncated=False, duration_ms=1)


def masked(
    sql: str, source: SourcePolicy, *rows: tuple[object, ...]
) -> tuple[tuple[object, ...], ...]:
    """Validate `sql`, pretend the engine answered `rows`, return the masked rows."""
    validated = validate(sql, source=source, max_rows=100)
    result = mask_frame(
        frame(tuple(projection.name for projection in validated.projections), *rows),
        validated.projections,
        styles_for(source.catalog),
    )
    return result.rows


# --- the shape of one value -------------------------------------------------


def test_an_email_keeps_its_shape() -> None:
    assert mask_value(PLANTED, "email") == "a***@l***.com"


def test_a_phone_keeps_its_last_four() -> None:
    assert mask_value("+44 20 7946 0958", "phone") == "***0958"


def test_auto_reads_the_shape_off_the_value() -> None:
    """The default. There is no stored "this column holds emails" to consult."""
    assert mask_value(PLANTED, "auto") == "a***@l***.com"
    assert mask_value("+44 20 7946 0958", "auto") == "***0958"
    assert mask_value("Ada Lovelace", "auto") == REDACTED


def test_last_four_and_hash_are_available() -> None:
    assert mask_value("4111111111111234", MASK_LAST4) == "***1234"
    hashed = mask_value("abc", MASK_HASH)
    assert isinstance(hashed, str) and hashed.startswith("sha256:")


def test_a_value_that_is_not_text_is_redacted_rather_than_reshaped() -> None:
    """A masked salary of `9****` still says it has five digits."""
    assert mask_value(91234, "email") == REDACTED
    assert mask_value(3.5, MASK_LAST4) == REDACTED


def test_null_stays_null() -> None:
    """ "This customer has no email" is not a secret about the customer."""
    assert mask_value(None, "email") is None


def test_an_unrecognised_style_redacts() -> None:
    assert mask_value(PLANTED, "something-new") == REDACTED


# --- which cells ------------------------------------------------------------


def test_a_masked_column_is_masked_in_the_result(either: SourcePolicy) -> None:
    rows = masked("SELECT email FROM customers", either, (PLANTED,))

    assert rows == (("a***@l***.com",),)
    assert PLANTED not in str(rows)


def test_an_allowed_column_beside_it_is_untouched(either: SourcePolicy) -> None:
    rows = masked("SELECT city, email FROM customers", either, ("London", PLANTED))

    assert rows[0][0] == "London"
    assert rows[0][1] == "a***@l***.com"


def test_an_expression_over_a_masked_column_is_masked(either: SourcePolicy) -> None:
    """`UPPER(email)` spells the address out just as well as `email` does."""
    rows = masked("SELECT UPPER(email) AS shout FROM customers", either, (PLANTED.upper(),))

    assert rows == ((REDACTED,),)


def test_an_alias_does_not_get_a_value_past_it(either: SourcePolicy) -> None:
    rows = masked("SELECT email AS contact FROM customers", either, (PLANTED,))

    assert rows == (("a***@l***.com",),)


def test_a_count_over_a_masked_column_is_a_number(either: SourcePolicy) -> None:
    """The distinction that makes `mask` more useful than `deny`."""
    rows = masked("SELECT COUNT(email) AS n FROM customers", either, (42,))

    assert rows == ((42,),)


def test_max_over_a_masked_column_is_masked(either: SourcePolicy) -> None:
    """MAX returns a value that was in the column. COUNT does not."""
    rows = masked("SELECT MAX(email) AS newest FROM customers", either, (PLANTED,))

    assert rows == ((REDACTED,),)


def test_two_columns_of_the_same_name_are_masked_by_position(either: SourcePolicy) -> None:
    """`SELECT c.city, c.email` returns two strings."""
    rows = masked(
        "SELECT c.email, s.full_name FROM customers c, public.staff s",
        either,
        (PLANTED, "Ada Lovelace"),
    )

    assert rows == (("a***@l***.com", REDACTED),)


def test_a_masked_column_used_only_in_a_predicate_returns_nothing_to_mask(
    either: SourcePolicy,
) -> None:
    """It never reaches the result, so there is no cell to mask."""
    validated = validate(
        "SELECT city FROM customers WHERE email LIKE '%@example.com'", source=either, max_rows=100
    )

    assert validated.touches_sensitive
    assert [projection.sensitive for projection in validated.projections] == [False]


def test_the_masked_columns_are_named_for_the_audit_row(either: SourcePolicy) -> None:
    validated = validate("SELECT city, email FROM customers", source=either, max_rows=100)
    result = mask_frame(
        frame(("city", "email"), ("London", PLANTED)),
        validated.projections,
        styles_for(either.catalog),
    )

    assert result.masked_columns == ("email",)


def test_a_result_that_does_not_match_its_description_is_masked_entirely(
    either: SourcePolicy,
) -> None:
    """Fails closed."""
    validated = validate("SELECT city FROM customers", source=either, max_rows=100)
    result = mask_frame(
        frame(("city", "email"), ("London", PLANTED)),
        validated.projections,
        styles_for(either.catalog),
    )

    assert result.rows == ((REDACTED, REDACTED),)
    assert result.masked_columns == ("city", "email")


def test_an_admins_choice_of_mask_wins_over_the_inferred_one() -> None:
    """`mask_type` is stored when an Admin decides one and was being dropped on the way out..."""
    catalog = build_catalog()
    customers = next(table for table in catalog.tables if table.table_name == "customers")
    email = next(column for column in customers.columns if column.name == "email")

    inferred = styles_for(catalog)
    assert inferred  # the fixture has masked columns at all

    object.__setattr__(email, "mask_type", MASK_HASH)
    chosen = styles_for(catalog)

    assert [style for ref, style in chosen.items() if ref.column == "email"] == [MASK_HASH]


@pytest.mark.parametrize(
    "value",
    ["ada@lovelace.example.com", "a@b.co", "no-at-sign", "@leading", "trailing@"],
)
def test_masking_an_address_never_returns_it(value: str) -> None:
    """Whatever shape it is in — the one thing that must always hold."""
    assert mask_value(value, "email") != value
