"""Sabotage(돌연변이) 테스트 — 가드가 살아있음을 증명. 깨지면 가드 회귀."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import run
from stockpick.backtest.fakes import (
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
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


def _cfg(start: date, end: date, **kw: object) -> BacktestConfig:
    base: dict[str, object] = dict(
        strategy_name="equal_weight_top_n",
        top_n=1,
        lookback_days=5,
        skip_recent_days=0,
        rebalance_freq="monthly",
        cost_bps=Decimal("0"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
        start=start,
        end=end,
    )
    base.update(kw)
    return BacktestConfig(**base)  # type: ignore[arg-type]


def test_lookahead_future_beyond_horizon_does_not_change_result() -> None:
    # config.end 이후 미래 데이터를 추가해도 결과 불변(지평 밖 미래 누설 차단).
    days = _weekdays(date(2024, 1, 1), 70)
    horizon = days[49]  # 50번째 거래일까지만 백테스트
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal("100")) for d in days]
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    cfg = _cfg(days[0], horizon)

    # 기준: horizon 까지만 데이터
    base_a = [p for p in a if p.trade_date <= horizon]
    base_b = [p for p in b if p.trade_date <= horizon]
    r_base = run(
        cfg,
        price_port=FakePriceSeriesPort({"A": base_a, "B": base_b}),
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
    )
    # sabotage: horizon 이후 미래에 A 가격을 폭등시켜 추가(누설되면 결과 바뀜)
    spiked = [
        *base_a,
        *[PricePoint(p.trade_date, Decimal("999999")) for p in a if p.trade_date > horizon],
    ]
    r_spiked = run(
        cfg,
        price_port=FakePriceSeriesPort({"A": spiked, "B": b}),
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
    )
    assert r_base.total_return == r_spiked.total_return
    assert r_base.equity_curve == r_spiked.equity_curve


def test_survivorship_excluding_delisted_changes_metrics() -> None:
    # 폐지종목 포함 vs 제외 → 지표 달라짐(생존편향이 결과에 영향 = 가드 살아있음).
    days = _weekdays(date(2024, 1, 1), 70)
    de = date(2024, 2, 15)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days) if d < de]
    b = [PricePoint(d, Decimal("100")) for d in days]
    port = FakePriceSeriesPort({"A": a, "B": b})
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    cfg = _cfg(days[0], days[-1])

    # 포함: A(폐지) + B
    uni_incl = FakeUniversePort(
        listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={"A": de}
    )
    r_incl = run(
        cfg,
        price_port=port,
        universe_port=uni_incl,
        identity=ident,
        strategy=EqualWeightTopN(),
    )
    # 제외: B 만(폐지 A 를 유니버스에서 빼버린 생존편향 시나리오)
    uni_excl = FakeUniversePort(listed={"B": date(2023, 1, 1)}, delisted={})
    r_excl = run(
        cfg,
        price_port=port,
        universe_port=uni_excl,
        identity=ident,
        strategy=EqualWeightTopN(),
    )
    # 폐지 A 손실이 포함된 결과와 제외 결과는 달라야 한다(가드가 결과를 바꾼다).
    assert r_incl.total_return != r_excl.total_return
    assert r_incl.n_delisted_liquidations >= 1
    assert r_excl.n_delisted_liquidations == 0
