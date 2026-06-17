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
    # 금액 봉인(차이만이 아니라 정확값): 폐지 A(recovery 0) 포함 → 전액 손실 -1.
    # 제외(B 평탄만) → 무손익 0. 발동 여부가 아니라 발동 금액을 봉인.
    assert r_incl.total_return == Decimal("-1")
    assert r_incl.n_delisted_liquidations >= 1
    assert r_excl.total_return == Decimal("0")
    assert r_excl.n_delisted_liquidations == 0


def test_rank_at_ignores_future_data() -> None:
    # 직접 룩어헤드 봉인: 동일 데이터 + as_of(t) **이후** B 가격 폭등 → as_of=t 랭킹 불변.
    # load(as_of=t)를 full_series()로 바꾸는 누설 회귀가 들어오면 이 단언이 깨진다.
    from stockpick.backtest.engine import _rank_at

    days = _weekdays(date(2024, 1, 1), 40)
    t = days[20]
    # ≤t 구간: A 가 B 보다 가파른 상승 → as_of=t 모멘텀 A > B (정상 랭킹 [A, B]).
    a = [PricePoint(d, Decimal(100 + 2 * i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    cfg = _cfg(days[0], days[-1], top_n=2)

    base = FakePriceSeriesPort({"A": a, "B": b})
    # sabotage: t 이후 B 를 폭등(누설되면 B 모멘텀이 A 를 추월해 랭킹이 [B, A]로 뒤집힘).
    b_spiked = [p if p.trade_date <= t else PricePoint(p.trade_date, Decimal("999999")) for p in b]
    spiked = FakePriceSeriesPort({"A": a, "B": b_spiked})

    r_base = _rank_at(cfg, base, uni, ident, base.ticker_exchanges(), t)
    r_spiked = _rank_at(cfg, spiked, uni, ident, spiked.ticker_exchanges(), t)
    assert [e.ticker for e in r_base] == [e.ticker for e in r_spiked]
    assert [e.ticker for e in r_base] == ["A", "B"]  # 정상: A 가 #1(미래 무관)
