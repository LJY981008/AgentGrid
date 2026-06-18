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

import argparse
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import configure_logging
from .db import connect, master_securities, update_stock_dates
from .eodhd import EodhdAuthError, EodhdRateLimitError, EodhdResponseError, EodhdSource
from .storage import build_expected, load_trade_date_bounds, verify_parquet, write_daily_bars

if TYPE_CHECKING:
    from collections.abc import Callable

    import psycopg
    from psycopg.rows import TupleRow

    from ..types import DailyBar
    from .storage import TickerExpectation

logger = logging.getLogger(__name__)

_DATA_DIR_ENV = "STOCKPICK_DATA_DIR"
_DEFAULT_DATA_DIR = "data/parquet"

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


def run_bulk(
    source: EodhdSource,
    *,
    base_dir: Path,
    conn: psycopg.Connection[TupleRow],
    limit: int | None = None,
    max_retries: int = 3,
    rate_sleep: float = 0.06,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """종목마스터 대상 다년 EOD → Parquet 벌크 + 날짜 backfill + verify 1회. 반환 = 커버리지 요약.

    재개(체크포인트 done/empty skip·failed 재시도). verify expected=**이번 run 성공 fetch 누적**
    (C1 — 마스터 전체 아님). 마스터-vs-fetch 갭은 요약(coverage)으로 고지. 커밋은 호출부.
    """
    securities = master_securities(conn)
    tickers = [t for t, _, _ in securities]
    if len(tickers) != len(set(tickers)):  # M1 — update_stock_dates ticker 키 안전 의존
        msg = f"마스터 ticker 비유일({len(tickers)} vs {len(set(tickers))} distinct) — 적재 중단"
        raise ValueError(msg)
    if limit is not None:
        securities = securities[:limit]

    checkpoint = Checkpoint.load(base_dir / _CHECKPOINT_NAME)
    expected: dict[str, TickerExpectation] = {}
    fetched = empty = failed = skipped = 0

    for ticker, exchange, _status in securities:
        if checkpoint.should_skip(ticker):
            skipped += 1
            continue
        try:
            bars = fetch_with_retry(source, ticker, max_retries=max_retries, sleep_fn=sleep_fn)
        except EodhdAuthError:
            raise  # 키/쿼터 — 전체 중단(체크포인트 증분 기록됨)
        except EodhdRateLimitError:
            logger.error(
                "일일쿼터 소진 추정 — 중단·재개 가능. 처리: done=%d empty=%d failed=%d",
                fetched,
                empty,
                failed,
            )
            raise  # graceful stop
        except EodhdResponseError:
            checkpoint.mark(ticker, "failed")
            failed += 1
            continue
        if not bars:
            checkpoint.mark(ticker, "empty")
            empty += 1
            continue
        write_daily_bars(bars, exchange=exchange, base_dir=base_dir, source=source.name)
        checkpoint.mark(ticker, "done")  # ⚠️ write 완료 후에만(M3)
        expected.update(build_expected(bars))
        fetched += 1
        if rate_sleep:
            sleep_fn(rate_sleep)

    # verify 1회(per-ticker 아님·O(n²) 회피) — 이번 run 성공분 소실 봉인.
    report = verify_parquet(base_dir, expected=expected)
    # 날짜 backfill(Parquet min/max → stock).
    update_stock_dates(conn, load_trade_date_bounds(base_dir))

    total = len(tickers)
    summary = {
        "master": total,
        "fetched": fetched,
        "empty": empty,
        "failed": failed,
        "skipped": skipped,
        "verify_passed": int(report.passed),
    }
    coverage = 100.0 * fetched / total if total else 0.0
    logger.info("벌크 적재 요약: %s · coverage(이번 run fetched/master)=%.1f%%", summary, coverage)
    return summary


def _parse_limit(argv: list[str] | None) -> int | None:
    parser = argparse.ArgumentParser(prog="stockpick.data.bulk")
    parser.add_argument("--limit", type=int, default=None, help="처리 ticker 수 제한(스모크/단계)")
    limit: int | None = parser.parse_args(argv).limit
    return limit


def main(argv: list[str] | None = None) -> int:
    """`python -m stockpick.data.bulk [--limit N]` — 마스터 대상 다년 EOD 벌크(진입점·commit).

    ⚠️ 전체 50,184 풀런은 수시간. `--limit` 로 스모크/단계 실행. 재개 가능(체크포인트).
    """
    configure_logging()  # G6 — httpx 토큰 로거 가드
    limit = _parse_limit(argv)
    base_dir = Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))
    source = EodhdSource()
    conn = connect()
    try:
        summary = run_bulk(source, base_dir=base_dir, conn=conn, limit=limit)
        conn.commit()
    finally:
        conn.close()
    print(f"[bulk] 벌크 가격 적재: {summary}")  # noqa: T201 — 진입점 출력
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
