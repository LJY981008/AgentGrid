"""ADR-010 PIT 유동성 필터 SQL(`query_liquid_tickers`) — 합성 cache.duckdb 경유 실측."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from stockpick.data.duckdb_cache import (
    build_cache,
    connect_readonly,
    query_liquid_tickers,
)
from stockpick.data.storage import write_daily_bars
from stockpick.types import DailyBar, Exchange


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bars(ticker: str, days: list[date], *, close: str, volume: int) -> list[DailyBar]:
    c = Decimal(close)
    return [
        DailyBar(
            ticker=ticker,
            trade_date=d,
            open=c,
            high=c,
            low=c,
            close=c,
            volume=volume,
            value=None,
            adj_factor=Decimal("1"),
        )
        for d in days
    ]


def _build(tmp_path: Path, bars: list[DailyBar]) -> Path:
    base = tmp_path / "parquet"
    base.mkdir()
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=base, source="t")
    build_cache(base)
    return base


def test_liquid_passes_price_and_adv(tmp_path: Path) -> None:
    days = _weekdays(date(2024, 1, 1), 25)
    # LIQ: close $10·vol 200k → ADV $2M·price $10. LOWP: close $2. LOWADV: vol 10k → ADV $100k.
    bars = (
        _bars("LIQ", days, close="10", volume=200_000)
        + _bars("LOWP", days, close="2", volume=200_000)
        + _bars("LOWADV", days, close="10", volume=10_000)
    )
    base = _build(tmp_path, bars)
    con = connect_readonly(base)
    try:
        out = query_liquid_tickers(
            con,
            as_of=days[-1],
            candidates={"LIQ", "LOWP", "LOWADV"},
            min_price=Decimal("5"),
            min_adv=Decimal("1000000"),
            window=20,
        )
    finally:
        con.close()
    assert out == {"LIQ"}  # LOWP 가격<$5·LOWADV ADV<$1M 제외


def test_insufficient_window_excluded(tmp_path: Path) -> None:
    days = _weekdays(date(2024, 1, 1), 25)
    bars = (
        _bars("FULL", days, close="10", volume=200_000)
        + _bars("SHORT", days[:5], close="10", volume=200_000)  # 5봉 < window 20
    )
    base = _build(tmp_path, bars)
    con = connect_readonly(base)
    try:
        out = query_liquid_tickers(
            con,
            as_of=days[-1],
            candidates={"FULL", "SHORT"},
            min_price=Decimal("5"),
            min_adv=Decimal("1000000"),
            window=20,
        )
    finally:
        con.close()
    assert out == {"FULL"}  # SHORT 봉<window → 유동성 미평가 제외(보수)


def test_lookahead_future_bars_ignored(tmp_path: Path) -> None:
    # 룩어헤드: as_of 이후 거래량 폭증이 as_of 판정을 바꾸면 안 됨.
    days = _weekdays(date(2024, 1, 1), 40)
    cut = days[24]  # as_of
    # 첫 25봉 비유동(ADV<$1M)·이후 폭증(유동). as_of=cut 이면 제외여야(미래 무시).
    low = _bars("X", days[:25], close="10", volume=10_000)
    high = _bars("X", days[25:], close="10", volume=500_000)
    base = _build(tmp_path, low + high)
    con = connect_readonly(base)
    try:
        out_at_cut = query_liquid_tickers(
            con,
            as_of=cut,
            candidates={"X"},
            min_price=Decimal("5"),
            min_adv=Decimal("1000000"),
            window=20,
        )
        out_later = query_liquid_tickers(
            con,
            as_of=days[-1],
            candidates={"X"},
            min_price=Decimal("5"),
            min_adv=Decimal("1000000"),
            window=20,
        )
    finally:
        con.close()
    assert out_at_cut == set()  # as_of 시점엔 비유동(미래 폭증 무시)
    assert out_later == {"X"}  # 폭증 후엔 유동(시점별 멤버십)
