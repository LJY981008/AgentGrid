"""S6-a 결과 불변 — load_range 전환이 백테스트 결과를 바꾸지 않음(실 DuckDB == Fake).

critic M4: Fake 메모리 슬라이스만으론 실 DuckDB 경계/타입을 못 잡는다. 동일 합성 데이터를
ParquetPriceSeriesPort(실 DuckDB load_range)와 FakePriceSeriesPort(메모리) 양쪽으로 백테스트해
equity_curve·지표·n_delisted 가 일치함을 봉인한다(폐지경계·보유 중 갭 포함).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from stockpick.backtest.adapters import ParquetPriceSeriesPort
from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import run
from stockpick.backtest.fakes import (
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.data.storage import write_daily_bars
from stockpick.rules._scan import PricePoint
from stockpick.types import DailyBar, Exchange

if TYPE_CHECKING:
    from pathlib import Path


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bars_from_series(series: dict[str, list[PricePoint]]) -> list[DailyBar]:
    # adj_factor=1 → adjusted=close=raw, Fake series 의 adjusted 와 동일 가격 적재.
    return [
        DailyBar(
            ticker=tk,
            trade_date=p.trade_date,
            open=p.adjusted,
            high=p.adjusted,
            low=p.adjusted,
            close=p.adjusted,
            volume=1000,
            value=None,
            adj_factor=Decimal("1"),
        )
        for tk, pts in series.items()
        for p in pts
    ]


def test_engine_parquet_load_range_matches_fake(tmp_path: Path) -> None:
    days = _weekdays(date(2024, 1, 1), 70)
    de = date(2024, 2, 15)  # A 폐지일(목요일·days 포함)
    # A: de 전까지(보유 중 폐지)·B: 평탄·C: 보유 중 갭(매월 20일 누락).
    series: dict[str, list[PricePoint]] = {
        "A": [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days) if d < de],
        "B": [PricePoint(d, Decimal("100")) for d in days],
        "C": [PricePoint(d, Decimal(120 + i)) for i, d in enumerate(days) if d.day != 20],
    }
    write_daily_bars(
        _bars_from_series(series),
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="test",
        ingested_at=datetime(2026, 6, 17, tzinfo=UTC),
    )
    cfg = BacktestConfig(
        strategy_name="equal_weight_top_n",
        top_n=2,
        lookback_days=20,  # _window_start 경계 강화(작은 lookback 미시험 회피·critic MEDIUM2)
        skip_recent_days=3,
        rebalance_freq="monthly",
        cost_bps=Decimal("0"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
        start=days[0],
        end=days[-1],
    )
    uni = FakeUniversePort(listed={t: date(2023, 1, 1) for t in series}, delisted={"A": de})
    idn = StubIdentityResolver({})
    strat = EqualWeightTopN()
    r_fake = run(
        cfg,
        price_port=FakePriceSeriesPort(series),
        universe_port=uni,
        identity=idn,
        strategy=strat,
    )
    r_parq = run(
        cfg,
        price_port=ParquetPriceSeriesPort(tmp_path),
        universe_port=uni,
        identity=idn,
        strategy=strat,
    )
    # 실 DuckDB load_range 경로 == Fake 메모리 경로(결과 불변·폐지청산·갭 동일 처리).
    assert r_parq.equity_curve == r_fake.equity_curve
    assert r_parq.total_return == r_fake.total_return
    assert r_parq.sharpe == r_fake.sharpe
    assert r_parq.max_drawdown == r_fake.max_drawdown
    assert r_parq.n_delisted_liquidations == r_fake.n_delisted_liquidations
    assert r_parq.n_delisted_liquidations >= 1  # A 폐지청산 발동(가드 살아있음)
