"""PG18 운영 서빙 repo — stock·ticker_history·daily_bar UPSERT + Parquet→PG 단방향 동기 (S5-a).

⚠️ Parquet 가 1차 진실원본(백테스트 DuckDB 스캔). PG 는 **파생 서빙**(운영 조회)이며 동기는
**단방향(Parquet→PG)**·멱등 UPSERT(ON CONFLICT). PG 직접 수정 금지(역류=1차 진실원본 오염).
접속은 `DATABASE_URL`(compose 제공) psycopg3.

⚠️ cik 경계 매핑(ADR-006·생존편향 BLOCKING): 코드베이스는 미해소 cik 를 `""`(빈 문자열)로 폴백한다
(`eodhd.py`·`edgar.py`). PG 부분 UNIQUE(`WHERE cik IS NOT NULL`)는 `""` 를 non-null 로 취급해
미해소 2번째 종목에서 충돌하므로, upsert 직전 `cik == ""` → SQL NULL 로 매핑한다(`types.Stock.cik:
str` 도메인 계약은 불변 — 경계 변환만). 미해소 다수가 NULL 로 공존(생존편향 누수 0).

⚠️ source·ingested_at 은 `types.Stock` 에 없으므로(도메인 계약) repo 파라미터로 받는다
(`write_daily_bars` 계약 미러). DELETE 금지(폐지는 delisted_at 으로만).

모듈 경계(python-conventions): `data` 층 — 상위(rules/backtest/api) import 금지.
의존은 psycopg3·duckdb·`..types` 만.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import psycopg
from psycopg.rows import TupleRow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date
    from pathlib import Path

    from ..types import Stock

logger = logging.getLogger(__name__)

_DATABASE_URL_ENV = "DATABASE_URL"
_DATASET_NAME = "daily_bar"

# ticker_history 한 행: (stock_id, ticker, cik|None, valid_from, valid_to|None).
TickerHistoryRow = tuple[int, str, "str | None", "date", "date | None"]


def connect() -> psycopg.Connection[TupleRow]:
    """DATABASE_URL(compose) 로 PG 접속(psycopg3). 미설정 시 RuntimeError."""
    url = os.environ.get(_DATABASE_URL_ENV, "")
    if not url:
        msg = f"환경변수 {_DATABASE_URL_ENV} 미설정 — PG 접속 URL 이 필요합니다(compose 제공)."
        raise RuntimeError(msg)
    return psycopg.connect(url)


def upsert_stocks(
    conn: psycopg.Connection[TupleRow],
    stocks: Sequence[Stock],
    *,
    source: str,
    ingested_at: datetime,
) -> int:
    """stock UPSERT(폐지 포함·DELETE 금지). 반환 = 처리 행수. 커밋은 호출부 책임.

    cik 해소 종목은 `ON CONFLICT(cik) DO UPDATE`(부분 UNIQUE 대상)로 갱신, 미해소(`cik==""`)는
    SQL NULL 매핑 후 INSERT(충돌 안 함 — 다수 NULL 공존, 생존편향). cik NULL 행의 멱등 재조정은
    S5-b(유니버스 reconciliation)에서. exchange 는 `::exchange_enum` 캐스트.
    """
    if not stocks:
        return 0
    sql = """
        INSERT INTO stock (cik, ticker, name, exchange, listed_at, delisted_at, source, ingested_at)
        VALUES (%s, %s, %s, %s::exchange_enum, %s, %s, %s, %s)
        ON CONFLICT (cik) WHERE cik IS NOT NULL DO UPDATE SET
            ticker = EXCLUDED.ticker, name = EXCLUDED.name, exchange = EXCLUDED.exchange,
            listed_at = EXCLUDED.listed_at, delisted_at = EXCLUDED.delisted_at,
            source = EXCLUDED.source, ingested_at = EXCLUDED.ingested_at
    """
    params = [
        (
            s.cik or None,  # "" → NULL(미해소 — 부분 UNIQUE 충돌 회피·생존편향)
            s.ticker,
            s.name,
            s.exchange.value,
            s.listed_at,
            s.delisted_at,
            source,
            ingested_at,
        )
        for s in stocks
    ]
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    logger.info("stock UPSERT: %d건(미해소 cik→NULL)", len(stocks))
    return len(stocks)


def upsert_ticker_history(
    conn: psycopg.Connection[TupleRow],
    rows: Sequence[TickerHistoryRow],
) -> int:
    """ticker_history UPSERT(시점별 ticker↔cik). PK(stock_id,ticker,valid_from) 충돌 시 갱신.

    rows = (stock_id, ticker, cik|None, valid_from, valid_to|None). 실제 유니버스 기반 채움은 S5-b.
    """
    if not rows:
        return 0
    sql = """
        INSERT INTO ticker_history (stock_id, ticker, cik, valid_from, valid_to)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (stock_id, ticker, valid_from) DO UPDATE SET
            cik = EXCLUDED.cik, valid_to = EXCLUDED.valid_to
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def sync_daily_bars_from_parquet(
    conn: psycopg.Connection[TupleRow],
    base_dir: Path,
) -> int:
    """Parquet(1차 진실) → PG daily_bar 단방향 동기. PK(ticker,trade_date) ON CONFLICT 멱등 UPSERT.

    ⚠️ COPY 아님(ON CONFLICT 미지원). DuckDB 로 Parquet 스캔 → executemany UPSERT. 룩어헤드는
    여기서 안 거른다(전체 동기 — 시점 필터는 랭킹/백테스트 쿼리 책임). 빈 트리면 no-op. 반환=행수.
    """
    dataset_root = base_dir / _DATASET_NAME
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        logger.info("동기 대상 Parquet 없음 — no-op: %s", dataset_root)
        return 0

    import duckdb

    glob = f"{dataset_root}/**/*.parquet"
    con = duckdb.connect(database=":memory:")
    try:
        # ⚠️ ingested_at(TIMESTAMPTZ)는 epoch_us(bigint)로 추출 — DuckDB tz-aware Python 변환은
        # pytz 의존(미설치). 마이크로초 정수로 받아 Python UTC datetime 재구성(원본 시각 보존).
        rows = con.execute(
            "SELECT ticker, trade_date, open, high, low, close, volume, value, adj_factor, "
            "source, epoch_us(ingested_at) AS ingested_us "
            "FROM read_parquet($glob, hive_partitioning=true) ORDER BY ticker, trade_date",
            {"glob": glob},
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return 0

    params = [(*row[:10], datetime.fromtimestamp(int(row[10]) / 1_000_000, tz=UTC)) for row in rows]
    sql = """
        INSERT INTO daily_bar (ticker, trade_date, open, high, low, close, volume, value,
            adj_factor, source, ingested_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker, trade_date) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close,
            volume = EXCLUDED.volume, value = EXCLUDED.value, adj_factor = EXCLUDED.adj_factor,
            source = EXCLUDED.source, ingested_at = EXCLUDED.ingested_at
    """
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    logger.info("daily_bar 동기(Parquet→PG): %d행 UPSERT", len(params))
    return len(params)


def find_orphan_tickers(conn: psycopg.Connection[TupleRow]) -> list[str]:
    """daily_bar 에 있으나 stock 마스터에 없는 ticker(D2 — FK 미강제 대체 사후검증). 정렬 반환."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT d.ticker FROM daily_bar d "
            "LEFT JOIN stock s ON s.ticker = d.ticker WHERE s.id IS NULL ORDER BY d.ticker"
        )
        return [str(row[0]) for row in cur.fetchall()]
