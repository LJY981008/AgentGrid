"""S5-b 종목마스터 적재 오케스트레이션 — EODHD Common Stock 유니버스 → PG stock/ticker_history.

흐름: `fetch_common_stock_universe`(활성/폐지 분리) → EDGAR cik enrich(`load_ticker_cik`) →
`upsert_stocks`(⚠️ **delisted 먼저 → active 나중** — resolved cik 충돌 시 active 승리·B1) →
`ticker_history` 현재 스냅샷(⚠️ **stock.id 당 1행**·floor sentinel — M-a). 단방향·멱등. 진입점
`main()` 이 configure_logging(G6 토큰 가드)·connect·commit.

⚠️ 단일 트랜잭션(마스터 규모 수만 행 — 원샷·멱등 UPSERT·실패 시 깨끗한 rollback+재실행). 청크/
체크포인트는 S5-c(다년 가격). 거래소는 EODHD "US"→OTC 다수(M2 한계·S5-d 정밀화). 날짜
(listed_at/delisted_at)는 S5-c 가 가격 min/max trade_date 로 backfill(EODHD 미제공).

모듈 경계(python-conventions): data 층 — 상위(rules/backtest/api) import 금지.
의존은 eodhd·edgar·db·types·stdlib 만.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from . import configure_logging
from .db import connect, upsert_stocks, upsert_ticker_history
from .edgar import load_ticker_cik
from .eodhd import EodhdSource

if TYPE_CHECKING:
    import psycopg
    from psycopg.rows import TupleRow

    from ..types import Stock
    from .db import TickerHistoryRow

logger = logging.getLogger(__name__)

# ticker_history 스냅샷 valid_from sentinel — 현 스냅샷이 전 구간 유효 가정(cik_for(ticker, on)
# 어떤 날짜도 해소). 시점별 ticker 재사용 해소·EXCLUDE 제약은 S5-d(실 history).
_SNAPSHOT_FLOOR = date(1900, 1, 1)
_DATA_DIR_ENV = "STOCKPICK_DATA_DIR"
_DEFAULT_DATA_DIR = "data/parquet"


def load_universe_master(
    source: EodhdSource,
    *,
    base_dir: Path,
    conn: psycopg.Connection[TupleRow],
    ingested_at: datetime,
) -> dict[str, int]:
    """Common Stock 유니버스 → stock UPSERT + ticker_history 스냅샷. 반환 = 카운트. 커밋은 호출부.

    cik enrich = EDGAR ticker_cik 저장본(해소 시 stock.cik·미해소 ""→NULL). delisted 먼저·active
    나중(active-wins on resolved cik). ticker_history 는 stock.id 당 1행(같은 ticker 2행이면 2행).
    """
    active, delisted = source.fetch_common_stock_universe(include_delisted=True)
    ticker_cik = load_ticker_cik(base_dir)

    def _enrich(stocks: list[Stock]) -> list[Stock]:
        # EDGAR ticker→cik 해소(미해소는 ""→upsert 가 NULL 매핑). ⚠️ .upper() 만으론 클래스주
        # 구두점 차(BRK-A vs BRK.A) 미해소 가능 — 매칭률은 라이브(Task6)로 진단.
        return [dataclasses.replace(s, cik=ticker_cik.get(s.ticker.upper(), "")) for s in stocks]

    active_e = _enrich(active)
    delisted_e = _enrich(delisted)

    # ⚠️ delisted 먼저 → active 나중: resolved cik 양 목록 공존 시 ON CONFLICT(cik) 로 active 승리.
    upsert_stocks(conn, delisted_e, source=source.name, ingested_at=ingested_at, status="delisted")
    upsert_stocks(conn, active_e, source=source.name, ingested_at=ingested_at, status="active")

    rows = _snapshot_ticker_history(conn)
    upsert_ticker_history(conn, rows)

    logger.info(
        "종목마스터 적재: active=%d, delisted=%d, ticker_history=%d(stock.id 당)",
        len(active_e),
        len(delisted_e),
        len(rows),
    )
    return {"active": len(active_e), "delisted": len(delisted_e), "ticker_history": len(rows)}


def _snapshot_ticker_history(conn: psycopg.Connection[TupleRow]) -> list[TickerHistoryRow]:
    """현재 stock 전 행 → ticker_history 스냅샷(stock.id 당 1행·floor→NULL). M-a: ticker 당 아님."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, ticker, cik FROM stock")
        return [
            (int(r[0]), str(r[1]), (str(r[2]) if r[2] is not None else None), _SNAPSHOT_FLOOR, None)
            for r in cur.fetchall()
        ]


def main() -> int:
    """`python -m stockpick.data.universe` — EODHD Common Stock → PG 마스터 적재(진입점)."""
    configure_logging()  # G6 — httpx 토큰 로거 가드(EODHD api_token URL 노출 차단)
    base_dir = Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))
    source = EodhdSource()
    conn = connect()
    try:
        result = load_universe_master(
            source, base_dir=base_dir, conn=conn, ingested_at=datetime.now(UTC)
        )
        conn.commit()
    finally:
        conn.close()
    print(  # noqa: T201 — 진입점 사용자 출력
        f"[universe] 종목마스터 적재 완료: active={result['active']}, "
        f"delisted={result['delisted']}, ticker_history={result['ticker_history']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
