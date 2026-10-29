"""Prices: exact Decimal cost formula per P05.8."""

from decimal import Decimal

import pytest

from charie.shared.ai.errors import AiError
from charie.shared.ai.prices import call_cost


def test_cost_formula() -> None:
    cost = call_cost("muse-wonder-1.0", 1_000_000, 200_000, 100_000)
    assert cost == Decimal("5.24")


def test_unknown_model_refused() -> None:
    with pytest.raises(AiError):
        call_cost("gpt-99", 10, 0, 0)
