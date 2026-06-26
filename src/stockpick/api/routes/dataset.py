"""GET /api/dataset — 적재된 data/parquet 트리 요약(DuckDB 집계).

⚠️ 모듈 경계: api 는 상위 모듈이라 저장 레이아웃(data.storage 의 daily_bar Hive 트리)을 **읽기만**
한다(쓰기·변형 없음). SQL injection 가드는 _scan.py·storage.py 규약과 동일 — 경로는 $glob 파라미터
바인딩으로만 주입(사용자 입력이 SQL 에 안 섞임). 여기 glob 은 사용자 입력이 아니라 서버 설정
base_dir 에서 합성한 값이지만, 동일 규약을 지켜 일관성·안전을 유지한다.

빈 트리(파일 없음) → 모든 카운트 0·빈 배열·sources []·날짜 null. 200(에러 아님 — 첫 실행 정상 상태).
"""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends

from ...types import Exchange
from ..deps import get_base_dir
from ..models import DatasetSummary, DatasetTicker

logger = logging.getLogger(__name__)

router = APIRouter()

_DATASET_NAME = "daily_bar"

# ticker별 집계: exchange(Hive 파티션 키), 행수, 기간, source(파일 내부 컬럼). 경로는 $glob 바인딩.
_SQL_PER_TICKER = (  # noqa: S608 — 골격 리터럴, 경로는 파라미터 바인딩($glob)
    "SELECT ticker, max(exchange) AS exchange, count(*) AS row_count, "
    "min(trade_date) AS min_date, max(trade_date) AS max_date, max(source) AS source "
    "FROM read_parquet($glob, hive_partitioning=true) "
    "GROUP BY ticker ORDER BY ticker"
)


def _empty_summary() -> DatasetSummary:
    return DatasetSummary(
        ticker_count=0,
        total_rows=0,
        min_date=None,
        max_date=None,
        sources=[],
        tickers=[],
    )


def _coerce_date(value: object) -> date | None:
    """DuckDB DATE → datetime.date 좁히기. 예상 밖 타입은 추측 변환 없이 실패(실패 명확 보고)."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    msg = f"예상치 못한 날짜 타입: {type(value)}"
    raise TypeError(msg)


@router.get("/dataset", response_model=DatasetSummary)
def dataset(base_dir: Path = Depends(get_base_dir)) -> DatasetSummary:
    dataset_root = base_dir / _DATASET_NAME
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        logger.info("dataset 요약: Parquet 트리 비어있음 — 빈 요약 반환: root=%s", dataset_root)
        return _empty_summary()

    import duckdb

    # `:memory:` memory_limit 캡(MEM-fix) — 무설정=호스트RAM 80% → full Parquet 스캔 RSS 폭발(실측
    # 12.95G·_scan/storage 동형). 캡→spill·결과 불변. env STOCKPICK_SCAN_MEMORY_LIMIT(기본 1GB).
    mlimit = os.environ.get("STOCKPICK_SCAN_MEMORY_LIMIT", "1GB")
    glob = f"{dataset_root}/**/*.parquet"
    con = duckdb.connect(database=":memory:", config={"memory_limit": mlimit})
    try:
        rows = con.execute(_SQL_PER_TICKER, {"glob": glob}).fetchall()
    finally:
        con.close()

    tickers: list[DatasetTicker] = []
    sources: set[str] = set()
    total_rows = 0
    min_dates: list[date] = []
    max_dates: list[date] = []

    for row in rows:
        ticker, exchange_str, row_count, min_d, max_d, source = row
        if not (isinstance(ticker, str) and isinstance(exchange_str, str)):
            msg = f"예상치 못한 집계 행 타입: ticker={type(ticker)}, exchange={type(exchange_str)}"
            raise TypeError(msg)
        if not isinstance(row_count, int):
            msg = f"row_count 타입 예상 밖: {type(row_count)}"
            raise TypeError(msg)
        mn = _coerce_date(min_d)
        mx = _coerce_date(max_d)
        src = source if isinstance(source, str) else None
        if src is not None:
            sources.add(src)
        total_rows += row_count
        if mn is not None:
            min_dates.append(mn)
        if mx is not None:
            max_dates.append(mx)
        tickers.append(
            DatasetTicker(
                ticker=ticker,
                exchange=Exchange(exchange_str),
                row_count=row_count,
                min_date=mn,
                max_date=mx,
                source=src,
            )
        )

    summary = DatasetSummary(
        ticker_count=len(tickers),
        total_rows=total_rows,
        min_date=min(min_dates) if min_dates else None,
        max_date=max(max_dates) if max_dates else None,
        sources=sorted(sources),
        tickers=tickers,
    )
    logger.info(
        "dataset 요약: tickers=%d, total_rows=%d, sources=%s",
        summary.ticker_count,
        summary.total_rows,
        summary.sources,
    )
    return summary
