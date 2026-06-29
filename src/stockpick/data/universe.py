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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from . import configure_logging
from .db import connect, upsert_stocks, upsert_ticker_history
from .edgar import load_ticker_cik
from .eodhd import EodhdSource

if TYPE_CHECKING:
    from collections.abc import Sequence

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


def build_ticker_history_rows(
    stocks: list[tuple[int, str, str | None, date | None, date | None]],
    recovered: dict[str, tuple[str, date]],
) -> list[TickerHistoryRow]:
    """stock 행(+A1 복구 cik) → ticker_history 실 다행. valid_from=listed_at·valid_to=delisted_at+1.

    stocks 행 = (stock_id, ticker, cik|None, listed_at|None, delisted_at|None). cik 우선순위
    stock.cik > recovered[ticker] > None. listed_at None(무가격)·degenerate(listed≥delisted) 제외
    (MasterUniverse 정렬·거래 불가). ⚠️ 폐지 엔티티는 cik 미해소여도 윈도우 유지(누락 시 재사용
    ticker 과거 시점이 미래 cik 로 누설·BLOCKING). 재사용=stock_id 당 1행(비중첩 다행). 중첩은
    detect_overlaps 가 관측(resolver 다중매칭 raise 전 경고).
    """
    rows: list[TickerHistoryRow] = []
    for stock_id, ticker, stock_cik, listed_at, delisted_at in stocks:
        if listed_at is None:
            continue  # 무가격 마스터 — 거래 윈도우 없음
        if delisted_at is not None and listed_at >= delisted_at:
            continue  # degenerate — 하루도 거래 불가(MasterUniverse 정렬)
        cik = stock_cik or (recovered[ticker][0] if ticker in recovered else None)
        valid_to = delisted_at + timedelta(days=1) if delisted_at is not None else None
        rows.append((stock_id, ticker, cik, listed_at, valid_to))
    overlaps = detect_overlaps(rows)
    if overlaps:
        logger.warning(
            "ticker_history 중첩 윈도우 %d ticker(추정 폐지일 오차·resolver raise 대상): %s",
            len(overlaps),
            ", ".join(overlaps[:10]),
        )
    return rows


def detect_overlaps(rows: Sequence[TickerHistoryRow]) -> list[str]:
    """같은 ticker 의 윈도우 [valid_from, valid_to) 가 겹치는 ticker 정렬 리스트(무결성 관측성).

    중첩 = 모호한 시점 식별 → resolver 다중매칭 raise 대상. valid_to None=+∞(개구간). 빈=무결성 OK.
    valid_from 정렬 후 인접쌍만 검사(정렬되면 i 가 i+2 와 겹치면 i+1 과도 겹침 → 인접 검사로 충분).
    """
    by_ticker: dict[str, list[tuple[date, date | None]]] = {}
    for _stock_id, ticker, _cik, valid_from, valid_to in rows:
        by_ticker.setdefault(ticker, []).append((valid_from, valid_to))
    flagged: list[str] = []
    for ticker, windows in by_ticker.items():
        if len(windows) < 2:
            continue
        ordered = sorted(windows, key=lambda w: w[0])
        for (_f1, t1), (f2, _t2) in zip(ordered, ordered[1:], strict=False):
            if t1 is None or f2 < t1:  # 선행 윈도우가 +∞이거나 후행 시작이 선행 끝 이전 → 중첩
                flagged.append(ticker)
                break
    return sorted(flagged)


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
