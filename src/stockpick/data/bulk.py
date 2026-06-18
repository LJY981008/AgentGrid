"""S5-c 벌크 가격 적재 오케스트레이터 — 종목마스터 대상 다년 EOD → Parquet(백테스트 진실원본).

흐름(run_bulk): ticker 유일 assert → master_securities → 체크포인트 skip(done/empty) → ticker별
fetch_with_retry → write_daily_bars(G1) → 체크포인트 기록 → **verify 끝에 1회**(per-ticker O(n²)
회피) → load_trade_date_bounds → update_stock_dates(날짜 backfill) → 커버리지 요약.
Parquet 벌크만(PG daily_bar 동기 이연). `meta.validated=false` 불변(데이터≠검증).

⚠️ 재개(G4): 체크포인트(JSONL)가 **유일한 진실원천** — write 는 (ticker,year) 파일단위 atomic
(per-ticker 아님)이라 중단 시 부분 ticker 가능, list_dataset_tickers 신뢰 불가. write 완료 후에만
done 기록. 재실행은 read-merge-write 멱등이라 부분 완성.

모듈 경계(python-conventions): data 층 — 상위(rules/backtest/api) import 금지.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from .eodhd import EodhdRateLimitError, EodhdResponseError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from ..types import DailyBar
    from .eodhd import EodhdSource

logger = logging.getLogger(__name__)

_CHECKPOINT_NAME = "bulk_checkpoint.jsonl"
_SKIP_STATUSES = frozenset({"done", "empty"})  # 재개 시 skip(failed 는 재시도)
_HTTP_SERVER_ERROR = 500
_MAX_BACKOFF_SECONDS = 60.0


def _backoff_seconds(attempt: int) -> float:
    """지수 backoff(attempt 1→2s, 2→4s, …) 상한 _MAX_BACKOFF_SECONDS."""
    return min(2.0**attempt, _MAX_BACKOFF_SECONDS)


class Checkpoint:
    """ticker 처리 상태 {ticker: 'done'|'empty'|'failed'} — JSONL append(O(1)). 재개 진실원천.

    append-only 라인(`ticker\\tstatus`) — 같은 ticker 재기록 시 마지막 라인 우선(load 가 순차 덮음).
    크래시 시 마지막 라인 부분기록 가능 → load 가 형식불량 라인 skip(보수적·재시도 회복).
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._status: dict[str, str] = {}

    @classmethod
    def load(cls, path: Path) -> Checkpoint:
        cp = cls(path)
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                parts = line.split("\t")
                if len(parts) == 2 and parts[0]:
                    cp._status[parts[0]] = parts[1]  # 마지막 기록 우선
        return cp

    def mark(self, ticker: str, status: str) -> None:
        """⚠️ write_daily_bars 완료 **후에만** 호출(M3 — write→체크포인트 순서)."""
        self._status[ticker] = status
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"{ticker}\t{status}\n")

    def should_skip(self, ticker: str) -> bool:
        """done/empty 면 skip(재개). failed/미기록 은 (재)처리 대상."""
        return self._status.get(ticker, "") in _SKIP_STATUSES

    def counts(self) -> dict[str, int]:
        tally = {"done": 0, "empty": 0, "failed": 0}
        for status in self._status.values():
            if status in tally:
                tally[status] += 1
        return tally


def fetch_with_retry(
    source: EodhdSource,
    ticker: str,
    *,
    max_retries: int = 3,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[DailyBar]:
    """`fetch_daily_bars` + 재시도. 반환=bars(0행 가능). 분류:

    - `EodhdRateLimitError` → retry_after_seconds(없으면 backoff) 대기 후 재시도. max 초과 시 raise
      (호출부가 일일쿼터 graceful stop 판단).
    - `EodhdResponseError` transient(status_code>=500 또는 None=timeout/transport) → backoff 재시도.
      per-ticker 4xx(<500) → raise(호출부 failed 기록).
    - `EodhdAuthError` → 전파(키/쿼터 — 전체 중단). 여기서 잡지 않음.
    """
    attempt = 0
    while True:
        try:
            return source.fetch_daily_bars(ticker)
        except EodhdRateLimitError as exc:
            attempt += 1
            if attempt > max_retries:
                raise
            wait = exc.retry_after_seconds or _backoff_seconds(attempt)
            logger.warning(
                "rate limit(429) %s — %.1fs 후 재시도(%d/%d)", ticker, wait, attempt, max_retries
            )
            sleep_fn(wait)
        except EodhdResponseError as exc:
            if exc.status_code is not None and exc.status_code < _HTTP_SERVER_ERROR:
                raise  # per-ticker 4xx — 호출부 failed 기록
            attempt += 1
            if attempt > max_retries:
                raise
            logger.warning(
                "transient(%s) %s — 재시도(%d/%d)", exc.status_code, ticker, attempt, max_retries
            )
            sleep_fn(_backoff_seconds(attempt))
