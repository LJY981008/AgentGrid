"""S6-a 결과 불변 — load_range 전환이 백테스트 결과를 바꾸지 않음(실 DuckDB == Fake).

critic M4: Fake 메모리 슬라이스만으론 실 DuckDB 경계/타입을 못 잡는다. 동일 합성 데이터를
ParquetPriceSeriesPort(실 DuckDB load_range)와 FakePriceSeriesPort(메모리) 양쪽으로 백테스트해
equity_curve·지표·n_delisted 가 일치함을 봉인한다(폐지경계·보유 중 갭 포함).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from stockpick.backtest.adapters import (
    DuckDBPriceSeriesPort,
    ParquetPriceSeriesPort,
    _close_price_port,
)
from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import run
from stockpick.backtest.fakes import (
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.data.duckdb_cache import build_cache
from stockpick.data.storage import write_daily_bars
from stockpick.rules._scan import PricePoint
from stockpick.types import DailyBar, Exchange

if TYPE_CHECKING:
    from pathlib import Path

# 시나리오: A=보유 중 폐지(de)·B=평탄·C=보유 중 갭(매월 20일 누락) — 폐지청산·갭 가드 동시 시험.
_SCENARIO_DELIST = date(2024, 2, 15)  # A 폐지일(목요일·거래일 포함)


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


def _scenario(
    tmp_path: Path,
) -> tuple[
    dict[str, list[PricePoint]],
    list[date],
    dict[str, Exchange],
    FakeUniversePort,
    StubIdentityResolver,
    EqualWeightTopN,
]:
    """폐지(A)·평탄(B)·갭(C) 합성 적재 + 공통 universe. A,B=NASDAQ·C=NYSE(거래소 그룹핑 검증).

    Parquet 트리만 기록(DuckDB 캐시는 호출부가 build_cache). Fake exchange 매핑이 실 파티션과
    일치하게 exchanges 맵도 반환(group_by_exchange=True 시 그룹핑 키 동일 → 세 포트 동치 비교).
    """
    days = _weekdays(date(2024, 1, 1), 70)
    de = _SCENARIO_DELIST
    series: dict[str, list[PricePoint]] = {
        "A": [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days) if d < de],
        "B": [PricePoint(d, Decimal("100")) for d in days],
        "C": [PricePoint(d, Decimal(120 + i)) for i, d in enumerate(days) if d.day != 20],
    }
    exchanges = {"A": Exchange.NASDAQ, "B": Exchange.NASDAQ, "C": Exchange.NYSE}
    stamp = datetime(2026, 6, 17, tzinfo=UTC)
    write_daily_bars(
        _bars_from_series({"A": series["A"], "B": series["B"]}),
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="test",
        ingested_at=stamp,
    )
    write_daily_bars(
        _bars_from_series({"C": series["C"]}),
        exchange=Exchange.NYSE,
        base_dir=tmp_path,
        source="test",
        ingested_at=stamp,
    )
    uni = FakeUniversePort(listed={t: date(2023, 1, 1) for t in series}, delisted={"A": de})
    return series, days, exchanges, uni, StubIdentityResolver({}), EqualWeightTopN()


def _make_cfg(days: list[date], *, group_by_exchange: bool) -> BacktestConfig:
    return BacktestConfig(
        strategy_name="equal_weight_top_n",
        top_n=2,
        lookback_days=20,  # _window_start 경계 강화(작은 lookback 미시험 회피·critic MEDIUM2)
        skip_recent_days=3,
        rebalance_freq="monthly",
        cost_bps=Decimal("0"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=group_by_exchange,
        start=days[0],
        end=days[-1],
    )


def test_engine_parquet_load_range_matches_fake(tmp_path: Path) -> None:
    series, days, exchanges, uni, idn, strat = _scenario(tmp_path)
    cfg = _make_cfg(days, group_by_exchange=False)
    r_fake = run(
        cfg,
        price_port=FakePriceSeriesPort(series, exchanges),
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


def test_engine_duckdb_port_matches_parquet_and_fake(tmp_path: Path) -> None:
    """DuckDBPriceSeriesPort 백테스트 == Parquet == Fake (Task5 BLOCKING·결과 bit-identical).

    ⚠️ Task6(engine momentum_scores 분기)의 가드레일: DuckDB 는 momentum_scores(SQL 부분 푸시다운)
    경로, Parquet/Fake 는 load_range+momentum_universe 경로 — 결과가 bit-identical 해야 한다.
    **group_by_exchange False·True 양쪽** 검증(True 는 ticker_to_exchange 가 그룹핑 키라 매핑 변경에
    가장 민감 — 폐지경계 A·갭 C·평탄 B·2거래소 포함).
    """
    series, days, exchanges, uni, idn, strat = _scenario(tmp_path)
    n = build_cache(tmp_path)  # Parquet → cache.duckdb(DuckDB 포트 입력)
    assert n == sum(len(pts) for pts in series.values())

    for gbe in (False, True):
        cfg = _make_cfg(days, group_by_exchange=gbe)
        r_fake = run(
            cfg,
            price_port=FakePriceSeriesPort(series, exchanges),
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
        dport = DuckDBPriceSeriesPort(tmp_path)
        try:
            r_duck = run(cfg, price_port=dport, universe_port=uni, identity=idn, strategy=strat)
        finally:
            _close_price_port(dport)

        assert r_duck.equity_curve == r_parq.equity_curve == r_fake.equity_curve, f"gbe={gbe}"
        assert r_duck.total_return == r_parq.total_return, f"gbe={gbe}"
        assert r_duck.cagr == r_parq.cagr, f"gbe={gbe}"
        assert r_duck.sharpe == r_parq.sharpe, f"gbe={gbe}"
        assert r_duck.sortino == r_parq.sortino, f"gbe={gbe}"
        assert r_duck.max_drawdown == r_parq.max_drawdown, f"gbe={gbe}"
        assert r_duck.turnover == r_parq.turnover, f"gbe={gbe}"
        assert r_duck.total_cost == r_parq.total_cost, f"gbe={gbe}"
        assert r_duck.n_rebalances == r_parq.n_rebalances, f"gbe={gbe}"
        assert r_duck.n_delisted_liquidations == r_parq.n_delisted_liquidations, f"gbe={gbe}"
        assert r_duck.n_delisted_liquidations >= 1, f"gbe={gbe}"  # A 폐지청산(생존편향 가드)
