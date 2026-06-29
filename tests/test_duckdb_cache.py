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


def test_build_cache_includes_financial_fact_table(tmp_path: Path) -> None:
    # A3: financial_fact Parquet 가 있으면 cache.duckdb 에 동봉 table(B DuckDB 푸시다운 입력).
    from stockpick.data.storage import write_financial_facts
    from stockpick.types import FinancialFact

    _write(tmp_path)  # daily_bar 필수(없으면 build_cache early-return)
    write_financial_facts(
        [
            FinancialFact(
                "0000000001", "NetIncomeLoss", "2024-FY",
                date(2024, 12, 31), date(2025, 1, 15), Decimal("200"),
            )
        ],
        tmp_path,
        source="sec-edgar",
        ingested_at=datetime(2026, 6, 29, tzinfo=UTC),
    )
    build_cache(tmp_path)
    con = connect_readonly(tmp_path)
    try:
        cnt = con.execute("SELECT count(*) FROM financial_fact").fetchone()
        assert cnt is not None and cnt[0] == 1
        v = con.execute("SELECT value FROM financial_fact WHERE cik='0000000001'").fetchone()
        assert v is not None and v[0] == Decimal("200")
    finally:
        con.close()


def test_build_cache_without_financial_fact_ok(tmp_path: Path) -> None:
    # 재무 미적재(백필 전)여도 build_cache 정상(financial_fact table 없을 뿐).
    _write(tmp_path)
    build_cache(tmp_path)
    con = connect_readonly(tmp_path)
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        assert "daily_bar" in tables
        assert "financial_fact" not in tables  # 백필 전 — 미생성(graceful)
    finally:
        con.close()
