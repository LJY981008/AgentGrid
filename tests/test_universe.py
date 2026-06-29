"""data/universe.py 오케스트레이션 테스트 — EODHD 모킹(httpx) + compose postgres(rollback 격리).

⚠️ DATABASE_URL 미연결 시 skip. 라이브 외부데이터 0(EODHD=MockTransport·PG=로컬 인프라).
검증: Common Stock 필터·active/delisted status·cik EDGAR enrich(해소/미해소)·ticker_history
stock.id 당 1행(M-a)·delisted→active 순서.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import psycopg
import pytest
from psycopg.rows import TupleRow

from stockpick.backtest.identity import PitIdentityResolver
from stockpick.data import cik_mapping, db
from stockpick.data.edgar import store_ticker_cik
from stockpick.data.eodhd import EodhdSource
from stockpick.data.universe import load_universe_master, rebuild_ticker_history
from stockpick.types import Exchange, Stock

_Conn = psycopg.Connection[TupleRow]
_STAMP = datetime(2026, 6, 18, tzinfo=UTC)
_KEY = "test-token-DO-NOT-LOG"


def _stock(ticker: str, *, cik: str = "") -> Stock:
    return Stock(
        cik=cik, ticker=ticker, name=ticker, exchange=Exchange.NASDAQ,
        listed_at=None, delisted_at=None,
    )


@pytest.fixture(autouse=True)
def _set_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EODHD_API_KEY", _KEY)


@pytest.fixture
def conn() -> Iterator[_Conn]:
    try:
        c = db.connect()
    except (RuntimeError, psycopg.OperationalError) as exc:
        pytest.skip(f"PG 미연결 — universe 테스트 skip: {exc!r}")
    try:
        # 트랜잭션 내 TRUNCATE — 커밋된 마스터와 격리. rollback 이 복원(sequence 보존).
        with c.cursor() as cur:
            cur.execute("TRUNCATE stock, ticker_history, daily_bar CASCADE")
        yield c
        c.rollback()
    finally:
        c.close()


def _source() -> EodhdSource:
    """활성=AAPL(common)+SPY(ETF·필터됨), 폐지=LEHMQ(common) 반환하는 MockTransport 소스."""

    def _handler(request: httpx.Request) -> httpx.Response:
        is_delisted = request.url.params.get("delisted") == "1"
        if is_delisted:
            rows: list[dict[str, object]] = [
                {"Code": "LEHMQ", "Name": "Lehman", "Exchange": "US", "Type": "Common Stock"},
            ]
        else:
            rows = [
                {"Code": "AAPL", "Name": "Apple", "Exchange": "US", "Type": "Common Stock"},
                {"Code": "SPY", "Name": "SPDR", "Exchange": "US", "Type": "ETF"},
            ]
        return httpx.Response(200, json=rows)

    return EodhdSource(client=httpx.Client(transport=httpx.MockTransport(_handler)))


def test_load_universe_master(conn: _Conn, tmp_path: Path) -> None:
    store_ticker_cik({"AAPL": "0000320193"}, tmp_path)  # AAPL 해소·LEHMQ 미해소
    result = load_universe_master(_source(), base_dir=tmp_path, conn=conn, ingested_at=_STAMP)
    assert result == {"active": 1, "delisted": 1}  # ETF 제외·ticker_history 는 finalize 소유

    with conn.cursor() as cur:
        cur.execute("SELECT ticker, cik, listing_status FROM stock ORDER BY ticker")
        got = [(r[0], r[1], r[2]) for r in cur.fetchall()]
    assert ("AAPL", "0000320193", "active") in got  # 해소 cik·active
    assert ("LEHMQ", None, "delisted") in got  # 미해소 cik NULL·delisted
    assert all(t != "SPY" for t, _, _ in got)  # ETF 미적재

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ticker_history")
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 0  # master-load 는 ticker_history 미적재(날짜 NULL → finalize 가 실 다행 빌드)


def test_rebuild_ticker_history_real_windows_and_resolver(conn: _Conn, tmp_path: Path) -> None:
    # 실 다행 빌드 + export + PitIdentityResolver 왕복: active 개구간·폐지 경계·A1 복구 cik.
    db.upsert_stocks(conn, [_stock("LIVE", cik="0000000901")], source="eodhd", ingested_at=_STAMP)
    db.upsert_stocks(
        conn, [_stock("GONE")], source="eodhd", ingested_at=_STAMP, status="delisted"
    )  # 폐지·cik 미해소(NULL)
    db.update_stock_dates(
        conn,
        {
            "LIVE": (date(2010, 1, 1), date(2025, 1, 1)),
            "GONE": (date(2000, 1, 1), date(2008, 9, 15)),
        },
    )
    cik_mapping.store_delisted_ciks({"GONE": ("0000000902", date(2008, 9, 15))}, tmp_path)

    n = rebuild_ticker_history(conn, tmp_path)
    assert n == 2  # LIVE(개구간)·GONE(경계)
    db.export_ticker_history_snapshot(conn, tmp_path)

    r = PitIdentityResolver(tmp_path)
    assert r.cik_for("LIVE", on=date(2020, 1, 1)) == "0000000901"  # active stock.cik
    assert r.cik_for("GONE", on=date(2005, 1, 1)) == "0000000902"  # A1 복구 cik(stock NULL 보완)
    assert r.cik_for("GONE", on=date(2008, 9, 15)) == "0000000902"  # 마지막 실거래일 포함
    assert r.cik_for("GONE", on=date(2008, 9, 16)) == ""  # 폐지 경계(delisted+1) 배제


def test_rebuild_ticker_history_idempotent(conn: _Conn, tmp_path: Path) -> None:
    # 재실행 시 clear+rebuild → 행 중복 0(파생 투영 멱등).
    db.upsert_stocks(conn, [_stock("IDEM", cik="0000000903")], source="eodhd", ingested_at=_STAMP)
    db.update_stock_dates(conn, {"IDEM": (date(2010, 1, 1), date(2025, 1, 1))})
    assert rebuild_ticker_history(conn, tmp_path) == 1
    assert rebuild_ticker_history(conn, tmp_path) == 1  # 중복 누적 없음
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ticker_history")
        row = cur.fetchone()
    assert row is not None
    assert row[0] == 1
