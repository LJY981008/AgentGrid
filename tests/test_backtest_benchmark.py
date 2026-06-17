from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from stockpick.backtest.benchmark import attach_benchmarks, equal_weight_universe
from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import run
from stockpick.backtest.fakes import (
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.metrics import BacktestResult
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.rules._scan import PricePoint


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


def test_equal_weight_flat_universe_zero_return() -> None:
    # 전부 평탄 → 등가중 벤치 수익 0.
    days = _weekdays(date(2024, 1, 1), 70)
    flat = {t: [PricePoint(d, Decimal("100")) for d in days] for t in ("A", "B")}
    port = FakePriceSeriesPort(flat)
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    bench = equal_weight_universe(_cfg(days), price_port=port, universe_port=uni)
    assert bench.total_return == Decimal("0")


def test_equal_weight_single_member_tracks_that_stock() -> None:
    # 유니버스에 1종목만 → 벤치 = 그 종목 수익(상승 → >0).
    days = _weekdays(date(2024, 1, 1), 70)
    rising = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"A": rising})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1)}, delisted={})
    bench = equal_weight_universe(_cfg(days), price_port=port, universe_port=uni)
    assert bench.total_return > Decimal("0")


def test_attach_benchmarks_injects_excess_comparison() -> None:
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal("100")) for d in days]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    cfg = _cfg(days)
    result = run(
        cfg, price_port=port, universe_port=uni, identity=ident, strategy=EqualWeightTopN()
    )
    bench = equal_weight_universe(cfg, price_port=port, universe_port=uni)
    merged = attach_benchmarks(result, {"EQUAL_WEIGHT_UNIVERSE": bench})
    assert "EQUAL_WEIGHT_UNIVERSE" in merged.benchmark_returns
    assert isinstance(merged.benchmark_returns["EQUAL_WEIGHT_UNIVERSE"], float)
    assert isinstance(merged, BacktestResult)
