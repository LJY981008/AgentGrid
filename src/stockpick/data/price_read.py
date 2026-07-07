"""티커·기간 한정 **raw close** 로더 — 추적 루프(M4) 성과 계산 전용(스펙 §5·C-1).

`rules/_scan.load_range_series` 는 adjusted(close×adj_factor) 합성인데 adj_factor 는 **분할+배당
혼합**(total-return 계수·`_adjust.py`)이라 price return 계산에 쓰면 배당 혼입 왜곡 — 여기서는
raw close 그대로 반환하고 분할 보정은 tracking 이 SPLIT 이벤트로 수행한다(수정주가 정의 통일
BLOCKING 의 명시 분리). 모듈 경계: tracking 은 data 만 의존 — rules 재사용 대신 이 로더.

DuckDB `:memory:` + memory_limit 캡(_scan MEM-fix 관례)·읽기 전용·빈 입력=빈 맵(조용한 추측 금지).
"""

from __future__ import annotations

import logging
import os
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_DATASET_NAME: Final = "daily_bar"
_MEMORY_LIMIT: Final = os.environ.get("STOCKPICK_SCAN_MEMORY_LIMIT", "1GB")

_FROM: Final = "FROM read_parquet($glob, hive_partitioning=true)"
_SQL_RAW_RANGE: Final = (  # noqa: S608 — SQL 골격은 리터럴·값은 파라미터 바인딩
    f"SELECT ticker, trade_date, close {_FROM} "
    "WHERE ticker = ANY($tickers) AND trade_date BETWEEN $start AND $end "
    "ORDER BY ticker, trade_date"
)
_SQL_MAX_DATES: Final = (  # noqa: S608
    f"SELECT ticker, max(trade_date) {_FROM} WHERE ticker = ANY($tickers) GROUP BY ticker"
)


def _run_query(
    base_dir: Path, sql: str, params: dict[str, object]
) -> list[tuple[object, ...]]:
    """dataset 글롭에 sql 실행(빈 트리=빈 결과). 연결은 memory_limit 캡·즉시 close."""
    dataset_root = base_dir / _DATASET_NAME
    if not any(dataset_root.rglob("*.parquet")):
        logger.warning("raw 스캔 대상 Parquet 없음 — 빈 결과: dataset=%s", dataset_root)
        return []

    import duckdb

    con = duckdb.connect(database=":memory:", config={"memory_limit": _MEMORY_LIMIT})
    try:
        rows = con.execute(sql, {"glob": f"{dataset_root}/**/*.parquet", **params}).fetchall()
    finally:
        con.close()
    return [tuple(row) for row in rows]


def load_raw_close_range(
    base_dir: Path,
    *,
    tickers: set[str],
    start: date,
    end: date,
) -> dict[str, list[tuple[date, Decimal]]]:
    """종목집합 × [start, end] 의 (trade_date, raw close) 오름차순 — adj_factor **미합성**.

    룩어헤드 상한은 호출부가 `end=as_of` 로 보장(≤t 데이터만). 무데이터 종목은 키 자체 없음
    (명시 부재 — 폐지/미수집 구분은 상위 as-of/폐지 규약 책임).
    """
    if not tickers:
        return {}
    out: dict[str, list[tuple[date, Decimal]]] = {}
    for row in _run_query(
        base_dir, _SQL_RAW_RANGE, {"tickers": sorted(tickers), "start": start, "end": end}
    ):
        ticker_v, date_v, close_v = row
        if (
            not isinstance(ticker_v, str)
            or not isinstance(date_v, date)
            or not isinstance(close_v, Decimal)
        ):
            msg = f"raw close 행 타입 위반: {row!r}"
            raise TypeError(msg)
        out.setdefault(ticker_v, []).append((date_v, close_v))
    logger.info(
        "raw close 로드: 요청 %d종목 중 %d종목, window=[%s..%s]",
        len(tickers),
        len(out),
        start,
        end,
    )
    return out


def load_max_trade_dates(base_dir: Path, *, tickers: set[str]) -> dict[str, date]:
    """종목별 max(trade_date) — 공통 as-of(활성 종목 min) 산출 입력. 무데이터=키 없음."""
    if not tickers:
        return {}
    out: dict[str, date] = {}
    for row in _run_query(base_dir, _SQL_MAX_DATES, {"tickers": sorted(tickers)}):
        ticker_v, date_v = row
        if not isinstance(ticker_v, str) or not isinstance(date_v, date):
            msg = f"max trade_date 행 타입 위반: {row!r}"
            raise TypeError(msg)
        out[ticker_v] = date_v
    return out
