"""The explanation checks, against plain column facts (P07.9, no database)."""

from charie.learner.steps.explain_tables import ExplainColumn, ExplainTableForm, check_explanation


def _form(**overrides) -> ExplainTableForm:
    columns = overrides.pop("columns", [])
    return ExplainTableForm(
        table_meaning=overrides.pop("table_meaning", "Orders are what customers buy."),
        grain=overrides.pop("grain", "one order"),
        columns=columns,
        **overrides,
    )


def _column(name: str = "total", **overrides) -> ExplainColumn:
    values = {"name": name, "meaning": "What the customer paid.", "unit": "money"}
    values.update(overrides)
    return ExplainColumn(**values)


COLUMNS = {
    "total": {
        "family": "numeric",
        "data_type": "numeric",
        "min": 1.5,
        "max": 400.0,
        "distinct": 118,
    },
    "status": {"family": "text", "data_type": "text", "min": None, "max": None, "distinct": 1},
    "qty": {"family": "integer", "data_type": "integer", "min": 1, "max": 25, "distinct": 20},
    "name": {"family": "text", "data_type": "text", "min": None, "max": None, "distinct": 3},
}
LINKS = [
    {
        "from_columns": ["store_id"],
        "to_table": "shop.stores",
        "to_title": "stores",
    }
]
SOURCE = '{"name": "orders", "columns": [{"name": "total"}]}'


def test_money_needs_a_number_column() -> None:
    form = _form(columns=[_column("status", meaning="How it ended.", unit="money")])
    failed = check_explanation(
        form, columns=COLUMNS, links=[], currency_codes=[], source_text=SOURCE
    )
    assert failed["status"] == ["Said to be money, but the column holds text."]


def test_count_cannot_be_negative() -> None:
    bad = dict(COLUMNS["qty"])
    bad["min"] = -1
    form = _form(columns=[_column("qty", meaning="How many items.", unit="count")])
    failed = check_explanation(
        form,
        columns={**COLUMNS, "qty": bad},
        links=[],
        currency_codes=[],
        source_text=SOURCE,
    )
    assert failed["qty"] == ["Said to be a count, but the smallest value is -1."]


def test_refers_to_must_match_a_link() -> None:
    form = _form(
        columns=[
            _column(
                "store_id",
                meaning="Which store sold it.",
                unit="id",
                refers_to="shop.restaurants",
            )
        ]
    )
    columns = {
        "store_id": {"family": "integer", "data_type": "integer", "min": 1, "max": 3, "distinct": 3}
    }
    failed = check_explanation(
        form, columns=columns, links=LINKS, currency_codes=[], source_text=SOURCE
    )
    assert failed["store_id"] == [
        "Said to point to shop.restaurants, but no tested link goes there."
    ]
    ok = _form(
        columns=[_column("store_id", meaning="Which store sold it.", unit="id", refers_to="stores")]
    )
    assert (
        check_explanation(ok, columns=columns, links=LINKS, currency_codes=[], source_text=SOURCE)
        == {}
    )


def test_currency_must_match_the_rule() -> None:
    form = _form(columns=[_column("total", currency="EUR")])
    failed = check_explanation(
        form, columns=COLUMNS, links=[], currency_codes=["USD"], source_text=SOURCE
    )
    assert failed["total"] == ["Said to be EUR, but money here is USD."]


def test_new_number_in_meaning_fails() -> None:
    form = _form(
        table_meaning="Orders are what 3 customers buy together.",
        columns=[_column("total", meaning="What the customer paid.")],
    )
    failed = check_explanation(
        form, columns=COLUMNS, links=[], currency_codes=[], source_text=SOURCE
    )
    assert failed == {"": ["Uses the number 3, which is not in the input."]}
