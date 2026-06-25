from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.fakes import (
    FakeLiquidityPort,
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.backtest.validation import decay_ratio, walk_forward
from stockpick.rules._scan import PricePoint


def test_decay_ratio_normal() -> None:
    r = decay_ratio(is_sharpe=2.0, oos_sharpe=1.0, epsilon=0.1)
    assert r.decay_ratio == 0.5
    assert r.decay_warning is True
    assert r.is_failed is False


def test_decay_is_failed_when_is_nonpositive() -> None:
    r = decay_ratio(is_sharpe=-0.5, oos_sharpe=1.0, epsilon=0.1)
    assert r.is_failed is True
    assert r.decay_ratio is None  # 분모 무의미 → None


def test_decay_none_when_is_below_epsilon() -> None:
    r = decay_ratio(is_sharpe=0.05, oos_sharpe=0.04, epsilon=0.1)
    assert r.decay_ratio is None  # 신호 미약 → 비율 산출 금지
    assert r.is_failed is False


def test_decay_no_warning_when_oos_holds_up() -> None:
    r = decay_ratio(is_sharpe=2.0, oos_sharpe=1.8, epsilon=0.1, warn_below=0.5)
    assert r.decay_ratio == 0.9
    assert r.decay_warning is False


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _cfg(days: list[date], **kw: object) -> BacktestConfig:
    base: dict[str, object] = dict(
        strategy_name="equal_weight_top_n",
        top_n=1,
        lookback_days=5,
        skip_recent_days=0,
        rebalance_freq="monthly",
        cost_bps=Decimal("0"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
        start=days[0],
        end=days[-1],
    )
    base.update(kw)
    return BacktestConfig(**base)  # type: ignore[arg-type]


def test_walk_forward_purge_gap_separates_is_oos() -> None:
    # 핵심: 각 fold 의 IS_end 와 OOS_start 사이에 정확히 purge 거래일이 비어야(룩백 누수 차단).
    days = _weekdays(date(2024, 1, 1), 250)  # ~1년
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal("100")) for d in days]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    purge = 5
    folds = walk_forward(
        _cfg(days, lookback_days=5),
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
        n_folds=2,
        purge_gap_days=purge,
    )
    assert len(folds) >= 1
    in_range = [d for d in days]
    for f in folds:
        # IS_end < d < OOS_start 인 거래일 수 == purge(정확히 그만큼 비움)
        between = [d for d in in_range if f.is_end < d < f.oos_start]
        assert len(between) == purge
        assert f.guard.purge_gap_days == purge
        assert f.is_end < f.oos_start


def test_walk_forward_insufficient_data_returns_empty() -> None:
    days = _weekdays(date(2024, 1, 1), 6)  # fold 분할에 부족
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"A": a})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1)}, delisted={})
    ident = StubIdentityResolver({"A": "CIK_A"})
    folds = walk_forward(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
        n_folds=3,
    )
    assert folds == []
