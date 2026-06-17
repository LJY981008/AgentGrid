"""엔진 테스트 — 결정적 합성 가격(라이브 0). 룩어헤드(진입 t+1)·폐지청산 검증."""

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


def test_rising_winner_grows_equity_no_delisting() -> None:
    # A 단조 상승, B 평탄 → top_n=1 은 매 리밸 A 선택 → equity 상승. 폐지 0.
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal("100")) for d in days]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    res = run(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"}),
        strategy=EqualWeightTopN(),
    )
    assert res.total_return > Decimal("0")
    assert res.n_delisted_liquidations == 0
    assert res.n_rebalances >= 1


def test_delisting_during_holding_realizes_total_loss() -> None:
    # A 보유 중 폐지(recovery_rate=0) → 그 구간 -100% → n_delisted>=1, 손실 반영.
    days = _weekdays(date(2024, 1, 1), 70)
    de = date(2024, 2, 15)  # 목요일 — days 에 포함
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days) if d < de]
    b = [PricePoint(d, Decimal("100")) for d in days]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(
        listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={"A": de}
    )
    res = run(
        _cfg(days, delisting_recovery_rate=Decimal("0")),
        price_port=port,
        universe_port=uni,
        identity=StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"}),
        strategy=EqualWeightTopN(),
    )
    assert res.n_delisted_liquidations >= 1
    # 금액 봉인: recovery_rate=0 → A(상승추세라 매 리밸 선택) 보유 중 폐지 = 그 기간 -100%
    # → 전액 손실. 이후 B(평탄)도 0 수익이라 최종 equity 0, total_return 정확히 -1.
    assert res.total_return == Decimal("-1")


def test_empty_universe_flat_equity() -> None:
    # 거래가능 종목 0 → 랭킹 빈 → 수익 0 → total_return 0.
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"A": a})
    uni = FakeUniversePort(listed={"A": date(2099, 1, 1)}, delisted={})  # 미래상장 → 항상 제외
    res = run(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=StubIdentityResolver({"A": "CIK_A"}),
        strategy=EqualWeightTopN(),
    )
    assert res.total_return == Decimal("0")
