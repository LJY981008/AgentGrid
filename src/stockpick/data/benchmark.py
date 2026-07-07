"""벤치마크(SPY) 가격 동기화 — **stock 마스터 밖 격리 서브트리**(스펙 §5·유니버스 오염 차단).

유니버스 수집은 common stock 전용(ETF 원천 배제·실측)이라 SPY 를 stock/daily_bar 본트리에
넣으면 랭킹·백테스트 유니버스가 오염된다 → `base_dir/"benchmark"` 서브트리에 기존
`write_daily_bars` 를 그대로 재사용해 격리 적재. 읽기는 `price_read.load_raw_close_range(
base_dir / BENCHMARK_SUBDIR, ...)` (전용 로더 불요).

벤치 티커 기본 = SPY(NYSE ARCA·ETF). 수집 실패는 소스 예외 그대로 전파(조용한 빈 벤치 금지 —
부재 시 성과 API 가 '측정불가' 표기 책임).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from ..types import Exchange
from .storage import write_daily_bars

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from .source import DataSource

logger = logging.getLogger(__name__)

BENCHMARK_SUBDIR: Final = "benchmark"
BENCHMARK_TICKER: Final = "SPY"


def sync_benchmark_prices(
    base_dir: Path,
    source: DataSource,
    *,
    start: date | None = None,
    end: date | None = None,
    ticker: str = BENCHMARK_TICKER,
) -> int:
    """벤치 티커 EOD 를 `base_dir/benchmark/daily_bar/...` 에 적재. 반환=행 수.

    0행이면 WARNING(소스 커버리지 문제 표면화 — 조용한 빈 벤치 금지). 멱등: write_daily_bars
    가 read-merge-write 라 재실행 안전(증분은 start 조정).
    """
    bars = source.fetch_daily_bars(ticker, start=start, end=end)
    if not bars:
        logger.warning(
            "벤치 수집 0행: ticker=%s, source=%s — 벤치 '측정불가' 유지", ticker, source.name
        )
        return 0
    write_daily_bars(
        bars,
        exchange=Exchange.NYSE_ARCA,
        base_dir=base_dir / BENCHMARK_SUBDIR,
        source=source.name,
    )
    logger.info("벤치 동기화: ticker=%s, %d행 → %s/", ticker, len(bars), BENCHMARK_SUBDIR)
    return len(bars)
