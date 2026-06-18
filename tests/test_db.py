"""data/db.py PG repo 테스트 — compose postgres 대상(라이브 외부데이터 0·PG=로컬 인프라).

⚠️ DATABASE_URL 미연결 시 skip(마커). 각 테스트는 트랜잭션 후 rollback(커밋 안 함 — 격리).
검증: 미해소 cik 2개 둘 다 적재(C1·생존편향)·cik 충돌 갱신·daily_bar 동기 멱등·고아 ticker 탐지.
스키마(alembic upgrade head)는 선행 적용 가정(로컬=실행중 PG·CI=pytest 전 upgrade).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import TupleRow

from stockpick.data import db
from stockpick.data.storage import write_daily_bars
from stockpick.types import DailyBar, Exchange, Stock

_Conn = psycopg.Connection[TupleRow]
_STAMP = datetime(2026, 6, 18, tzinfo=UTC)


@pytest.fixture
def conn() -> Iterator[_Conn]:
    try:
        c = db.connect()
    except (RuntimeError, psycopg.OperationalError) as exc:
        pytest.skip(f"PG 미연결 — db 테스트 skip: {exc!r}")
    try:
        yield c
        c.rollback()  # 커밋 안 함 — 테스트 격리(running PG 오염 방지)
    finally:
        c.close()


def _stock(ticker: str, *, cik: str = "", exchange: Exchange = Exchange.NASDAQ) -> Stock:
    return Stock(
        cik=cik, ticker=ticker, name=ticker, exchange=exchange, listed_at=None, delisted_at=None
    )


def _bar(ticker: str, d: date, *, adj_factor: str = "1") -> DailyBar:
    return DailyBar(
        ticker=ticker,
        trade_date=d,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=1000,
        value=None,
        adj_factor=Decimal(adj_factor),
    )


def _count(c: _Conn, sql: str, params: tuple[object, ...]) -> int:
    with c.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return int(row[0]) if row is not None else 0


def test_upsert_stocks_unresolved_cik_both_persist(conn: _Conn) -> None:
    # ⭐ C1 회귀(생존편향): 미해소 cik("") 2개 → 둘 다 적재(""→NULL·부분 UNIQUE 충돌 없음).
    db.upsert_stocks(conn, [_stock("ZZA"), _stock("ZZB")], source="eodhd", ingested_at=_STAMP)
    n = _count(
        conn,
        "SELECT count(*) FROM stock WHERE ticker IN (%s, %s) AND cik IS NULL",
        ("ZZA", "ZZB"),
    )
    assert n == 2


def test_upsert_stocks_resolved_cik_conflict_updates(conn: _Conn) -> None:
    db.upsert_stocks(conn, [_stock("ZZC", cik="0000000111")], source="eodhd", ingested_at=_STAMP)
    # 같은 cik, 다른 ticker 재적재 → 갱신(중복 0).
    db.upsert_stocks(conn, [_stock("ZZC2", cik="0000000111")], source="eodhd", ingested_at=_STAMP)
    assert _count(conn, "SELECT count(*) FROM stock WHERE cik = %s", ("0000000111",)) == 1
    with conn.cursor() as cur:
        cur.execute("SELECT ticker FROM stock WHERE cik = %s", ("0000000111",))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "ZZC2"  # 신규 ticker 로 갱신


def test_sync_daily_bars_idempotent(conn: _Conn, tmp_path: Path) -> None:
    bars = [_bar("ZZD", date(2024, 3, 1)), _bar("ZZD", date(2024, 3, 2))]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="eodhd")
    n1 = db.sync_daily_bars_from_parquet(conn, tmp_path)
    n2 = db.sync_daily_bars_from_parquet(conn, tmp_path)  # 재동기
    assert n1 == 2
    assert n2 == 2
    assert _count(conn, "SELECT count(*) FROM daily_bar WHERE ticker = %s", ("ZZD",)) == 2  # 멱등


def test_sync_daily_bars_decimal_precision(conn: _Conn, tmp_path: Path) -> None:
    # 정밀 BLOCKING: DuckDB decimal128 → fetchall Decimal → PG NUMERIC(38,10/12) 무손실 round-trip.
    # 정수 아닌 분수 가격·adj_factor 로 scale 보존 검증(float 다운캐스트면 깨짐).
    bar = DailyBar(
        ticker="ZZP",
        trade_date=date(2024, 5, 1),
        open=Decimal("129.0456"),
        high=Decimal("130.1111"),
        low=Decimal("128.0001"),
        close=Decimal("129.5000"),
        volume=1000,
        value=None,
        adj_factor=Decimal("0.987654321012"),  # scale 12 끝자리까지
    )
    write_daily_bars([bar], exchange=Exchange.NASDAQ, base_dir=tmp_path, source="eodhd")
    db.sync_daily_bars_from_parquet(conn, tmp_path)
    with conn.cursor() as cur:
        cur.execute("SELECT close, adj_factor FROM daily_bar WHERE ticker = %s", ("ZZP",))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == Decimal("129.5000")  # close NUMERIC(38,10) — 분수 정밀 보존
    assert row[1] == Decimal("0.987654321012")  # adj_factor NUMERIC(38,12) — scale 12 끝자리 보존


def test_find_orphan_tickers(conn: _Conn, tmp_path: Path) -> None:
    write_daily_bars(
        [_bar("ZZORPHAN", date(2024, 4, 1))],
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="eodhd",
    )
    db.sync_daily_bars_from_parquet(conn, tmp_path)
    assert "ZZORPHAN" in db.find_orphan_tickers(conn)  # stock 마스터에 없음 → 고아


def test_upsert_stocks_status_delisted(conn: _Conn) -> None:
    db.upsert_stocks(
        conn,
        [_stock("ZZDEL", cik="0000000222")],
        source="eodhd",
        ingested_at=_STAMP,
        status="delisted",
    )
    with conn.cursor() as cur:
        cur.execute("SELECT listing_status FROM stock WHERE cik = %s", ("0000000222",))
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "delisted"


def test_upsert_stocks_active_wins_on_cik_conflict(conn: _Conn) -> None:
    # B1: resolved cik — delisted 먼저 → active 나중 → ON CONFLICT(cik) active 승리.
    db.upsert_stocks(
        conn,
        [_stock("ZZW", cik="0000000333")],
        source="eodhd",
        ingested_at=_STAMP,
        status="delisted",
    )
    db.upsert_stocks(
        conn,
        [_stock("ZZW", cik="0000000333")],
        source="eodhd",
        ingested_at=_STAMP,
        status="active",
    )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), max(listing_status) FROM stock WHERE cik = %s", ("0000000333",)
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 1  # 1행 collapse(resolved cik)
    assert row[1] == "active"  # active-wins


def test_master_tickers(conn: _Conn) -> None:
    db.upsert_stocks(
        conn,
        [_stock("ZZM1"), _stock("ZZM2", cik="0000000444")],
        source="eodhd",
        ingested_at=_STAMP,
    )
    tickers = db.master_tickers(conn)
    assert "ZZM1" in tickers
    assert "ZZM2" in tickers
