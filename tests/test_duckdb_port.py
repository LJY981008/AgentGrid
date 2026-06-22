"""DuckDBPriceSeriesPort(Task3·ADR-007) — PriceSeriesPort + MomentumScorePort 구현 검증.

핵심(critic MAJOR-3): `DuckDBPriceSeriesPort.load_range` ↔ `ParquetPriceSeriesPort.load_range`
**행집합 동일**(BETWEEN 양경계·빈 tickers→{}·미존재 ticker·단일행 윈도우·adjusted Decimal 동등).
+ momentum_scores == momentum_universe(load_range windowed) bit-identical(엔진 경로 단위 동치).
+ Protocol 준수(isinstance)·연결 재사용. 라이브 0(합성 Parquet→build_cache).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from stockpick.backtest.adapters import (
    DuckDBPriceSeriesPort,
    ParquetPriceSeriesPort,
    _close_price_port,
    _select_price_port,
)
from stockpick.backtest.ports import (
    MomentumScorePort,
    PriceSeriesPort,
    momentum_window_days,
)
from stockpick.data.duckdb_cache import build_cache
from stockpick.data.storage import write_daily_bars
from stockpick.rules.factors import momentum_universe
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


def _bars(ticker: str, days: list[date], *, base: int, adj: str) -> list[DailyBar]:
    return [
        DailyBar(
            ticker=ticker,
            trade_date=d,
            open=Decimal(base + i),
            high=Decimal(base + i),
            low=Decimal(base + i),
            close=Decimal(base + i),
            volume=1000,
            value=None,
            adj_factor=Decimal(adj),
        )
        for i, d in enumerate(days)
    ]


def _build(tmp_path: Path) -> list[date]:
    """NASDAQ(AAA·BBB)+NYSE(CCC) 30봉 적재 + build_cache. 거래일 리스트 반환."""
    days = _weekdays(date(2024, 1, 1), 30)
    nasdaq = _bars("AAA", days, base=100, adj="1") + _bars("BBB", days, base=50, adj="1.25")
    nyse = _bars("CCC", days, base=200, adj="0.8")
    write_daily_bars(
        nasdaq,
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="test",
        ingested_at=datetime(2026, 6, 22, tzinfo=UTC),
    )
    write_daily_bars(
        nyse,
        exchange=Exchange.NYSE,
        base_dir=tmp_path,
        source="test",
        ingested_at=datetime(2026, 6, 22, tzinfo=UTC),
    )
    n = build_cache(tmp_path)
    assert n == len(nasdaq) + len(nyse)
    return days


def test_duckdb_port_protocol_conformance(tmp_path: Path) -> None:
    _build(tmp_path)
    port = DuckDBPriceSeriesPort(tmp_path)
    try:
        assert isinstance(port, PriceSeriesPort)  # runtime_checkable
        assert isinstance(port, MomentumScorePort)
    finally:
        port.close()


def test_load_range_equivalence_parquet(tmp_path: Path) -> None:
    """load_range 행집합이 Parquet 포트와 완전 동일(adjusted Decimal 포함)."""
    days = _build(tmp_path)
    dport = DuckDBPriceSeriesPort(tmp_path)
    pport = ParquetPriceSeriesPort(tmp_path)
    try:
        all_tickers = {"AAA", "BBB", "CCC"}
        cases: list[tuple[set[str], date, date]] = [
            (all_tickers, days[0], days[-1]),  # 전구간
            (all_tickers, days[5], days[20]),  # 내부 구간(BETWEEN 양경계 포함)
            ({"AAA"}, days[10], days[10]),  # 단일행 윈도우(start==end)
            ({"AAA", "ZZZ"}, days[0], days[-1]),  # 미존재 ticker(ZZZ) 섞임
            (set(), days[0], days[-1]),  # 빈 tickers → {}
        ]
        for tickers, start, end in cases:
            got = dport.load_range(tickers=tickers, start=start, end=end)
            want = pport.load_range(tickers=tickers, start=start, end=end)
            assert got == want, f"load_range 불일치: tickers={tickers}, [{start},{end}]"
        # 미존재 ticker 는 양쪽 모두 dict 에서 제외(조용한 빈리스트 금지)
        assert "ZZZ" not in dport.load_range(tickers={"AAA", "ZZZ"}, start=days[0], end=days[-1])
    finally:
        dport.close()


def test_load_and_full_series_equivalence(tmp_path: Path) -> None:
    days = _build(tmp_path)
    dport = DuckDBPriceSeriesPort(tmp_path)
    pport = ParquetPriceSeriesPort(tmp_path)
    try:
        # load(as_of) 룩어헤드 상한 — 중간 거래일 기준
        mid = days[15]
        assert dport.load(as_of=mid) == pport.load(as_of=mid)
        assert dport.full_series() == pport.full_series()
        assert dport.trading_days() == pport.trading_days()
        assert dport.ticker_exchanges() == pport.ticker_exchanges()
    finally:
        dport.close()


def test_momentum_scores_matches_memory_path(tmp_path: Path) -> None:
    """momentum_scores == momentum_universe(load_range windowed) — 엔진 메모리 경로 단위 동치.

    30봉 기준 다중 파라미터로 delegation 봉인: normal(10,2)·graceful 축소(100,0·lookback>봉수)·
    None(5,29·skip 과다로 end_idx<1). (sparse-window wn<total 발산은 test_momentum_pushdown GPART
    가 코어 레벨에서 봉인 — 여기선 포트 위임 정확성.)
    """
    days = _build(tmp_path)
    dport = DuckDBPriceSeriesPort(tmp_path)
    pport = ParquetPriceSeriesPort(tmp_path)
    try:
        as_of = days[-1]
        tickers = {"AAA", "BBB", "CCC"}
        for lookback, skip in [(10, 2), (100, 0), (5, 29)]:
            window_start = as_of - timedelta(days=momentum_window_days(lookback, skip))
            # 메모리 경로(진실원천) = load_range(windowed) + momentum_universe
            windowed = pport.load_range(tickers=tickers, start=window_start, end=as_of)
            want = momentum_universe(
                windowed, as_of=as_of, lookback_days=lookback, skip_recent_days=skip
            )
            got = dport.momentum_scores(
                tickers=tickers, as_of=as_of, lookback_days=lookback, skip_recent_days=skip
            )
            assert set(got) == set(want), f"(lb={lookback},skip={skip}) ticker 집합"
            for ticker, w in want.items():
                g = got[ticker]
                assert g.score == w.score, f"(lb={lookback},skip={skip}) {ticker} score"
                assert g.end_date == w.end_date, f"(lb={lookback},skip={skip}) {ticker} end"
                assert g.start_date == w.start_date, f"(lb={lookback},skip={skip}) {ticker} start"
                assert g.used_window_points == w.used_window_points, f"{ticker} used"
        # 빈 tickers → {}
        assert (
            dport.momentum_scores(tickers=set(), as_of=as_of, lookback_days=10, skip_recent_days=2)
            == {}
        )
    finally:
        dport.close()


def test_select_price_port_cache_present(tmp_path: Path) -> None:
    """cache.duckdb 존재 → DuckDBPriceSeriesPort(가속)."""
    _build(tmp_path)  # write + build_cache
    port = _select_price_port(tmp_path)
    try:
        assert isinstance(port, DuckDBPriceSeriesPort)
    finally:
        _close_price_port(port)


def test_select_price_port_cache_absent_fallback(tmp_path: Path) -> None:
    """cache.duckdb 부재 → ParquetPriceSeriesPort 폴백(기능 회귀 0·속도만 미가속)."""
    days = _weekdays(date(2024, 1, 1), 5)
    write_daily_bars(  # Parquet 만 기록·build_cache 안 함
        _bars("AAA", days, base=100, adj="1"),
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="test",
        ingested_at=datetime(2026, 6, 22, tzinfo=UTC),
    )
    port = _select_price_port(tmp_path)
    try:
        assert isinstance(port, ParquetPriceSeriesPort)
    finally:
        _close_price_port(port)


def test_select_price_port_corrupt_cache_fallback(tmp_path: Path) -> None:
    """부패 cache.duckdb(연결 실패) → ParquetPriceSeriesPort 폴백(반쪽 파일이 막지 않게)."""
    _build(tmp_path)
    (tmp_path / "cache.duckdb").write_bytes(b"not a valid duckdb file")  # 부패 주입
    port = _select_price_port(tmp_path)
    try:
        assert isinstance(port, ParquetPriceSeriesPort)
    finally:
        _close_price_port(port)


def test_close_price_port(tmp_path: Path) -> None:
    """_close_price_port: DuckDB 연결 해제(이후 사용 시 예외)·Parquet 포트는 no-op."""
    import duckdb

    _build(tmp_path)
    dport = DuckDBPriceSeriesPort(tmp_path)
    _close_price_port(dport)
    with pytest.raises(duckdb.Error):  # 닫힌 연결 사용 → loud fail
        dport.trading_days()
    _close_price_port(ParquetPriceSeriesPort(tmp_path))  # no-op(예외 없음)


def test_connection_reuse(tmp_path: Path) -> None:
    """단일 read_only 연결을 여러 호출에 재사용(매 호출 connect 안 함·S6-a critic C2)."""
    days = _build(tmp_path)
    port = DuckDBPriceSeriesPort(tmp_path)
    try:
        a = port.load_range(tickers={"AAA"}, start=days[0], end=days[-1])
        b = port.load_range(tickers={"BBB"}, start=days[0], end=days[-1])
        assert a and b  # 두 호출 모두 동일 연결로 성공
        assert port.trading_days()  # 연결 재사용 후에도 정상
    finally:
        port.close()
