from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from stockpick.backtest.benchmark import attach_benchmarks, equal_weight_universe
from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import run
from stockpick.backtest.fakes import (
    FakeLiquidityPort,
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.metrics import BacktestResult
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.rules._scan import PricePoint

_NOLIQ = FakeLiquidityPort(None)  # 필터 off(전종목 유동) — 유동성 외 동작 검증용


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
    bench = equal_weight_universe(
        _cfg(days), price_port=port, universe_port=uni, liquidity_port=_NOLIQ
    )
    assert bench.total_return == Decimal("0")


def test_equal_weight_single_member_tracks_that_stock() -> None:
    # 유니버스에 1종목만 → 벤치 = 그 종목 수익(상승 → >0).
    days = _weekdays(date(2024, 1, 1), 70)
    rising = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"A": rising})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1)}, delisted={})
    bench = equal_weight_universe(
        _cfg(days), price_port=port, universe_port=uni, liquidity_port=_NOLIQ
    )
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
        cfg,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=_NOLIQ,
    )
    bench = equal_weight_universe(cfg, price_port=port, universe_port=uni, liquidity_port=_NOLIQ)
    merged = attach_benchmarks(result, {"EQUAL_WEIGHT_UNIVERSE": bench})
    assert "EQUAL_WEIGHT_UNIVERSE" in merged.benchmark_returns
    assert isinstance(merged.benchmark_returns["EQUAL_WEIGHT_UNIVERSE"], float)
    assert isinstance(merged, BacktestResult)


# ── ADR-010 #5: 벤치 유동성 대칭 + 동일비용(M2 trap) ──


def test_benchmark_liquidity_filter_restricts_members() -> None:
    # 유동성 포트가 {"A"}만 통과 → 벤치 멤버에서 B(상승) 제외 → 평탄 A 만 → 수익 0(engine 과 대칭).
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal("100")) for d in days]  # 평탄
    b = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]  # 상승
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    cfg = _cfg(days)
    full = equal_weight_universe(
        cfg, price_port=port, universe_port=uni, liquidity_port=FakeLiquidityPort(None)
    )
    only_a = equal_weight_universe(
        cfg, price_port=port, universe_port=uni, liquidity_port=FakeLiquidityPort({"A"})
    )
    assert full.total_return > Decimal("0")  # A평탄+B상승 평균 → 상승
    assert only_a.total_return == Decimal("0")  # A 만 → 평탄


def test_benchmark_charges_cost_on_turnover() -> None:
    # M2: 동일비용 벤치 — cost_bps>0 이면 첫 진입 회전(buy)에 비용. turnover·total_cost 둘 다 >0
    # (둘 다 0이면 cost_bps 무효 = 무비용 벤치 = 불공정). 평탄 유니버스라 비용만큼 음수 수익.
    days = _weekdays(date(2024, 1, 1), 70)
    flat = {t: [PricePoint(d, Decimal("100")) for d in days] for t in ("A", "B")}
    port = FakePriceSeriesPort(flat)
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    cfg = _cfg(days, cost_bps=Decimal("10"))
    bench = equal_weight_universe(
        cfg, price_port=port, universe_port=uni, liquidity_port=FakeLiquidityPort(None)
    )
    assert bench.turnover > Decimal("0")
    assert bench.total_cost > Decimal("0")
    assert bench.total_return < Decimal("0")
