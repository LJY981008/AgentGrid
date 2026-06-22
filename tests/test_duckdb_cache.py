"""data/duckdb_cache.py — Parquet→.duckdb 파생 캐시(build/connect/exists·원자·멱등·중복 guard).

라이브 0(합성 Parquet via write_daily_bars·tmp). ADR-007.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from stockpick.data.duckdb_cache import build_cache, cache_exists, cache_path, connect_readonly
from stockpick.data.storage import write_daily_bars
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


def _bars(ticker: str, days: list[date]) -> list[DailyBar]:
    return [
        DailyBar(
            ticker=ticker,
            trade_date=d,
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal(100 + i),
            volume=1000,
            value=None,
            adj_factor=Decimal("1"),
        )
        for i, d in enumerate(days)
    ]


def _write(tmp_path: Path) -> int:
    days = _weekdays(date(2024, 1, 1), 5)
    bars = _bars("AAA", days) + _bars("BBB", days)
    write_daily_bars(
        bars,
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="test",
        ingested_at=datetime(2026, 6, 17, tzinfo=UTC),
    )
    return len(bars)


def test_build_cache_and_query(tmp_path: Path) -> None:
    n_bars = _write(tmp_path)
    n = build_cache(tmp_path)
    assert n == n_bars  # 10행(AAA·BBB × 5일)
    assert cache_exists(tmp_path)
    assert not (tmp_path / ".cache.duckdb.tmp").exists()  # 원자 교체 후 temp 정리됨
    con = connect_readonly(tmp_path)
    try:
        row = con.execute("SELECT count(*) FROM daily_bar").fetchone()
        assert row is not None and row[0] == n_bars
        # adjusted = close*adj_factor 합성 가능(부분푸시다운 입력)
        r = con.execute(
            "SELECT close*adj_factor FROM daily_bar WHERE ticker='AAA' ORDER BY trade_date LIMIT 1"
        ).fetchone()
        assert r is not None and r[0] == Decimal("100")
    finally:
        con.close()


def test_build_cache_idempotent(tmp_path: Path) -> None:
    n_bars = _write(tmp_path)
    assert build_cache(tmp_path) == n_bars
    assert build_cache(tmp_path) == n_bars  # 재실행 동일(전량 재생성)


def test_build_cache_empty(tmp_path: Path) -> None:
    assert build_cache(tmp_path) == 0
    assert not cache_exists(tmp_path)
    assert not cache_path(tmp_path).exists()
