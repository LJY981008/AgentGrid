"""data/bulk.py 체크포인트·재시도 — 라이브 0(httpx.MockTransport)·PG 불요(Task3 부분).

검증: 체크포인트 JSONL 라운드트립·done/empty skip·failed 재시도·마지막상태 우선 / fetch_with_retry
429 재시도·transient 5xx 재시도·4xx raise·auth 전파·429 소진 raise.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import psycopg
import pytest
from psycopg.rows import TupleRow

from stockpick.data import db
from stockpick.data.bulk import Checkpoint, fetch_with_retry, run_bulk
from stockpick.data.eodhd import (
    EodhdAuthError,
    EodhdRateLimitError,
    EodhdResponseError,
    EodhdSource,
)
from stockpick.data.storage import list_dataset_tickers
from stockpick.types import Exchange, Stock

_Conn = psycopg.Connection[TupleRow]
_STAMP = datetime(2026, 6, 18, tzinfo=UTC)

_EOD_ROW: dict[str, object] = {
    "date": "2024-01-02",
    "open": 1.0,
    "high": 1.0,
    "low": 1.0,
    "close": 1.0,
    "adjusted_close": 1.0,
    "volume": 1,
}


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EODHD_API_KEY", "test-token")


def _source(handler: httpx.MockTransport) -> EodhdSource:
    return EodhdSource(client=httpx.Client(transport=handler))


def _noop_sleep(_seconds: float) -> None:
    return None


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "cp.jsonl"
    cp = Checkpoint.load(p)
    cp.mark("AAA", "done")
    cp.mark("BBB", "empty")
    cp.mark("CCC", "failed")
    reloaded = Checkpoint.load(p)
    assert reloaded.should_skip("AAA")  # done → skip
    assert reloaded.should_skip("BBB")  # empty → skip
    assert not reloaded.should_skip("CCC")  # failed → 재시도
    assert not reloaded.should_skip("DDD")  # 미기록 → 처리
    assert reloaded.counts() == {"done": 1, "empty": 1, "failed": 1}


def test_checkpoint_last_status_wins(tmp_path: Path) -> None:
    p = tmp_path / "cp.jsonl"
    cp = Checkpoint.load(p)
    cp.mark("AAA", "failed")
    cp.mark("AAA", "done")  # 재처리 후 성공
    assert Checkpoint.load(p).should_skip("AAA")  # 마지막 done 우선


def test_fetch_with_retry_429_then_success() -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={}, headers={"Retry-After": "1"})
        return httpx.Response(200, json=[_EOD_ROW])

    bars = fetch_with_retry(_source(httpx.MockTransport(handler)), "AAA", sleep_fn=_noop_sleep)
    assert len(bars) == 1
    assert calls["n"] == 2  # 429 후 재시도 성공


def test_fetch_with_retry_transient_5xx_retried() -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=[_EOD_ROW])

    bars = fetch_with_retry(_source(httpx.MockTransport(handler)), "AAA", sleep_fn=_noop_sleep)
    assert len(bars) == 1
    assert calls["n"] == 2  # transient 5xx 재시도 성공


def test_fetch_with_retry_4xx_raises() -> None:
    # per-ticker 4xx(<500) → raise(호출부 failed 기록·계속).
    handler = httpx.MockTransport(lambda _r: httpx.Response(404, json={}))
    with pytest.raises(EodhdResponseError):
        fetch_with_retry(_source(handler), "AAA", sleep_fn=_noop_sleep)


def test_fetch_with_retry_auth_propagates() -> None:
    # auth(401) → 전파(전체 중단).
    handler = httpx.MockTransport(lambda _r: httpx.Response(401, json={}))
    with pytest.raises(EodhdAuthError):
        fetch_with_retry(_source(handler), "AAA", sleep_fn=_noop_sleep)


def test_fetch_with_retry_429_exhausts_raises() -> None:
    # 429 max_retries 초과 → raise(호출부 일일쿼터 graceful stop 판단).
    handler = httpx.MockTransport(lambda _r: httpx.Response(429, json={}))
    with pytest.raises(EodhdRateLimitError):
        fetch_with_retry(_source(handler), "AAA", max_retries=2, sleep_fn=_noop_sleep)


# ---- run_bulk 오케스트레이터 (PG·tmp Parquet·모킹 source) ----


@pytest.fixture
def conn() -> Iterator[_Conn]:
    try:
        c = db.connect()
    except (RuntimeError, psycopg.OperationalError) as exc:
        pytest.skip(f"PG 미연결 — run_bulk 테스트 skip: {exc!r}")
    try:
        with c.cursor() as cur:  # 트랜잭션 내 TRUNCATE — 커밋 마스터와 격리·rollback 복원
            cur.execute("TRUNCATE stock, ticker_history, daily_bar CASCADE")
        yield c
        c.rollback()
    finally:
        c.close()


def _eod(d: str) -> dict[str, object]:
    return {
        "date": d,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "adjusted_close": 1.0,
        "volume": 1,
    }


def _stock(ticker: str, *, exchange: Exchange) -> Stock:
    return Stock(
        cik="", ticker=ticker, name=ticker, exchange=exchange, listed_at=None, delisted_at=None
    )


def test_run_bulk(conn: _Conn, tmp_path: Path) -> None:
    # 마스터: AAA(active·2bar)·BBB(active·0bar empty)·DEAD(delisted·1bar).
    db.upsert_stocks(
        conn,
        [_stock("AAA", exchange=Exchange.NASDAQ), _stock("BBB", exchange=Exchange.NYSE)],
        source="eodhd",
        ingested_at=_STAMP,
    )
    db.upsert_stocks(
        conn,
        [_stock("DEAD", exchange=Exchange.OTC)],
        source="eodhd",
        ingested_at=_STAMP,
        status="delisted",
    )

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if "AAA" in url:
            return httpx.Response(200, json=[_eod("2020-01-02"), _eod("2021-01-04")])
        if "DEAD" in url:
            return httpx.Response(200, json=[_eod("2008-09-15")])
        return httpx.Response(200, json=[])  # BBB empty

    source = EodhdSource(client=httpx.Client(transport=httpx.MockTransport(handler)))
    summary = run_bulk(source, base_dir=tmp_path, conn=conn, sleep_fn=_noop_sleep)
    assert summary["master"] == 3
    assert summary["fetched"] == 2
    assert summary["empty"] == 1
    assert summary["verify_passed"] == 1
    assert set(list_dataset_tickers(tmp_path)) == {"AAA", "DEAD"}  # 0bar BBB 미적재

    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker, listed_at, delisted_at, delisted_at_source FROM stock "
            "WHERE ticker IN ('AAA', 'DEAD')"
        )
        rows = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    assert rows["AAA"] == (date(2020, 1, 2), None, None)  # active — delisted_at NULL
    assert rows["DEAD"] == (date(2008, 9, 15), date(2008, 9, 15), "eodhd_last_bar_estimate")

    # 재개: 2번째 run → done/empty 전부 skip(fetched 0).
    summary2 = run_bulk(source, base_dir=tmp_path, conn=conn, sleep_fn=_noop_sleep)
    assert summary2["skipped"] == 3
    assert summary2["fetched"] == 0


def test_run_bulk_limit(conn: _Conn, tmp_path: Path) -> None:
    db.upsert_stocks(
        conn,
        [_stock("AAA", exchange=Exchange.NASDAQ), _stock("BBB", exchange=Exchange.NYSE)],
        source="eodhd",
        ingested_at=_STAMP,
    )
    source = EodhdSource(
        client=httpx.Client(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=[_eod("2020-01-02")]))
        )
    )
    summary = run_bulk(source, base_dir=tmp_path, conn=conn, limit=1, sleep_fn=_noop_sleep)
    assert summary["fetched"] == 1  # --limit 1 — 첫 ticker만
