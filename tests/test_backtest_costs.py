from decimal import Decimal

import pytest

from stockpick.backtest.costs import apply_cost_fraction


def test_cost_fraction_basic() -> None:
    # turnover 1.0(전량 교체) × 10bps = 0.001
    assert apply_cost_fraction(Decimal("1.0"), Decimal("10")) == Decimal("0.0010")


def test_zero_turnover_zero_cost() -> None:
    assert apply_cost_fraction(Decimal("0"), Decimal("10")) == Decimal("0")


def test_negative_inputs_raise() -> None:
    with pytest.raises(ValueError, match="음수"):
        apply_cost_fraction(Decimal("-0.1"), Decimal("10"))
