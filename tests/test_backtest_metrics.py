import math
from datetime import date
from decimal import Decimal

from stockpick.backtest.metrics import compute_metrics


def test_known_equity_curve_metrics() -> None:
    curve = [
        (date(2024, 1, 1), Decimal("1.0")),
        (date(2024, 7, 1), Decimal("1.2")),
        (date(2024, 12, 31), Decimal("1.1")),
    ]
    period_returns = [Decimal("0.2"), Decimal("-0.0833333")]
    res = compute_metrics(
        curve,
        period_returns,
        periods_per_year=2,
        turnover_total=Decimal("2"),
        cost_total=Decimal("0.002"),
        n_rebalances=2,
        n_delisted=0,
        benchmark_returns={},
        caveats=("1년치",),
        config_fingerprint="abc",
    )
    assert res.total_return == Decimal("0.1")  # 1.1/1.0 - 1
    # MDD: 1.2→1.1 = -0.0833...
    assert math.isclose(res.max_drawdown, -0.0833333, rel_tol=1e-3)
    assert res.n_delisted_liquidations == 0
    assert res.data_caveats == ("1년치",)


def test_empty_curve_safe() -> None:
    res = compute_metrics(
        [],
        [],
        periods_per_year=12,
        turnover_total=Decimal("0"),
        cost_total=Decimal("0"),
        n_rebalances=0,
        n_delisted=0,
        benchmark_returns={},
        caveats=(),
        config_fingerprint="x",
    )
    assert res.total_return == Decimal("0")
    assert res.sharpe == 0.0
    assert res.cagr == 0.0


def test_max_drawdown_monotonic_up_is_zero() -> None:
    curve = [
        (date(2024, 1, 1), Decimal("1.0")),
        (date(2024, 6, 1), Decimal("1.1")),
        (date(2024, 12, 1), Decimal("1.3")),
    ]
    res = compute_metrics(
        curve,
        [Decimal("0.1"), Decimal("0.18")],
        periods_per_year=2,
        turnover_total=Decimal("0"),
        cost_total=Decimal("0"),
        n_rebalances=2,
        n_delisted=0,
        benchmark_returns={},
        caveats=(),
        config_fingerprint="x",
    )
    assert res.max_drawdown == 0.0


def test_sortino_no_downside_is_zero() -> None:
    # 하락 기간 없음 → 소르티노 0(분모 0 가드)
    res = compute_metrics(
        [(date(2024, 1, 1), Decimal("1.0")), (date(2024, 6, 1), Decimal("1.2"))],
        [Decimal("0.1"), Decimal("0.09")],
        periods_per_year=2,
        turnover_total=Decimal("0"),
        cost_total=Decimal("0"),
        n_rebalances=2,
        n_delisted=0,
        benchmark_returns={},
        caveats=(),
        config_fingerprint="x",
    )
    assert res.sortino == 0.0
