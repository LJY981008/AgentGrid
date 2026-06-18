"""data/universe.py 오케스트레이션 테스트 — EODHD 모킹(httpx) + compose postgres(rollback 격리).

⚠️ DATABASE_URL 미연결 시 skip. 라이브 외부데이터 0(EODHD=MockTransport·PG=로컬 인프라).
검증: Common Stock 필터·active/delisted status·cik EDGAR enrich(해소/미해소)·ticker_history
stock.id 당 1행(M-a)·delisted→active 순서.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import pytest
from psycopg.rows import TupleRow

from stockpick.data import db
from stockpick.data.edgar import store_ticker_cik
from stockpick.data.eodhd import EodhdSource
from stockpick.data.universe import load_universe_master

_Conn = psycopg.Connection[TupleRow]
_STAMP = datetime(2026, 6, 18, tzinfo=UTC)
_KEY = "test-token-DO-NOT-LOG"


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
    assert result == {"active": 1, "delisted": 1, "ticker_history": 2}  # ETF 제외

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
    assert row[0] == 2  # stock.id 당 1행(M-a)
