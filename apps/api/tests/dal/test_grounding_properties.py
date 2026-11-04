"""Generated identifiers never bypass grounding (plan §6 WP5.3)."""

from __future__ import annotations

from catalog_fixture import build_source
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from charie.dal.errors import PolicyViolation, ViolationCode
from charie.dal.policy import SourcePolicy
from charie.dal.validator import ColumnRef, validate

# Hypothesis runs each example against a fresh source; building the catalog is cheap but not free.
PROFILE = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


def _cased(word: str) -> st.SearchStrategy[str]:
    """Every case mixture of a word: `tax_id`, `TAX_ID`, `tAx_Id`, …"""
    return st.tuples(
        *[st.sampled_from([character.lower(), character.upper()]) for character in word]
    ).map("".join)


#: Characters that read as ASCII letters and are not.
HOMOGLYPHS = {"a": "а", "c": "с", "e": "е", "o": "о", "p": "р", "x": "х", "i": "і"}  # noqa: RUF001


def _homoglyphed(word: str) -> st.SearchStrategy[str]:
    def swap(index: int) -> str:
        character = word[index]
        return word[:index] + HOMOGLYPHS.get(character, character) + word[index + 1 :]

    swappable = [index for index, character in enumerate(word) if character in HOMOGLYPHS]
    if not swappable:  # pragma: no cover - every word here has one
        return st.just(word)
    return st.sampled_from(swappable).map(swap)


@given(spelling=_cased("tax_id"))
@PROFILE
def test_a_denied_column_stays_denied_however_it_is_cased(spelling: str) -> None:
    """Unquoted identifiers fold, so every one of these is the same column."""
    source = build_source("pg")

    try:
        validate(f"SELECT {spelling} FROM customers", source=source, max_rows=100)
    except PolicyViolation as violation:
        assert violation.code is ViolationCode.DENIED_COLUMN
        return
    raise AssertionError(f"{spelling!r} was allowed; it is public.customers.tax_id")


@given(spelling=_cased("customers"))
@PROFILE
def test_a_table_resolves_however_it_is_cased(spelling: str) -> None:
    """The other side of the same coin: folding must not make a real table unreachable."""
    source = build_source("pg")

    result = validate(f"SELECT id FROM {spelling}", source=source, max_rows=100)

    assert str(result.tables[0]) == "public.customers"


@given(spelling=_homoglyphed("email"))
@PROFILE
def test_a_lookalike_column_is_refused_by_name(spelling: str) -> None:
    """A Cyrillic ye makes a different identifier."""
    source = build_source("pg")

    try:
        validate(f"SELECT {spelling} FROM customers", source=source, max_rows=100)
    except PolicyViolation as violation:
        assert violation.code in {
            ViolationCode.UNKNOWN_COLUMN,
            ViolationCode.PARSE_ERROR,
        }
        return
    raise AssertionError(f"{spelling!r} resolved to something; it is not in the catalog")


@given(spelling=_homoglyphed("customers"))
@PROFILE
def test_a_lookalike_table_is_refused_by_name(spelling: str) -> None:
    source = build_source("pg")

    try:
        validate(f"SELECT id FROM {spelling}", source=source, max_rows=100)
    except PolicyViolation as violation:
        assert violation.code in {ViolationCode.UNKNOWN_TABLE, ViolationCode.PARSE_ERROR}
        return
    raise AssertionError(f"{spelling!r} resolved to a table; it is not in the catalog")


@given(
    name=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), max_codepoint=0x24F),
        min_size=1,
        max_size=24,
    )
)
@PROFILE
def test_anything_that_validates_touched_only_catalogued_columns(name: str) -> None:
    """The blunt property, over anything that can be spelled."""
    source = build_source("pg")
    catalogued = {
        str(ColumnRef(table.schema_name, table.table_name, column.name))
        for table in source.catalog.tables
        for column in table.columns
    }

    try:
        result = validate(f"SELECT {name} FROM customers", source=source, max_rows=100)
    except PolicyViolation:
        return

    assert {str(column) for column in result.columns} <= catalogued
    assert {str(table) for table in result.tables} == {"public.customers"}


@given(spelling=_cased("tax_id"))
@PROFILE
def test_a_denied_column_stays_denied_in_a_predicate(spelling: str) -> None:
    """Casing plus position: the two dimensions that a rule applied only to the select list."""
    source = build_source("pg")

    try:
        validate(f"SELECT id FROM customers WHERE {spelling} = '1'", source=source, max_rows=100)
    except PolicyViolation as violation:
        assert violation.code is ViolationCode.DENIED_COLUMN
        return
    raise AssertionError(f"{spelling!r} was allowed in a predicate")


@given(cased=_cased("tax_id"), homoglyphed=_homoglyphed("email"))
@PROFILE
def test_the_generators_produce_what_they_claim(cased: str, homoglyphed: str) -> None:
    """A guard on the guards: a strategy that silently produced one value would make every..."""
    assert cased.lower() == "tax_id"
    assert homoglyphed != "email"
    assert homoglyphed.lower() != "email"


def test_both_dialects_agree_about_a_denied_column(either: SourcePolicy) -> None:
    """Not generated, but the same property across engines."""
    try:
        validate("SELECT TAX_ID FROM customers", source=either, max_rows=100)
    except PolicyViolation as violation:
        assert violation.code is ViolationCode.DENIED_COLUMN
        return
    raise AssertionError("a denied column was allowed")
