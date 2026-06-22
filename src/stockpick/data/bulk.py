"""S5-c 벌크 가격 적재 오케스트레이터 — 종목마스터 대상 다년 EOD → Parquet(백테스트 진실원본).

흐름(run_bulk): master_securities → 체크포인트 skip(done/empty) → fetch_with_retry →
write_daily_bars(G1) → 체크포인트 기록 → 후처리 `_apply_dates_and_snapshot`
(update_stock_dates → export_stock_snapshot) → 커버리지 요약.
⚠️ commit 은 호출부(main/CLI) — 코어 commit 금지(test rollback 격리·critic C1).
`verify_parquet` 은 `--verify` 옵션(기본 off·예외격리·S6 전 1회 게이트).
`--finalize` 는 적재 skip·후처리만(복구·멱등). Parquet 벌크만. `meta.validated=false` 불변.

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
from .db import connect, export_stock_snapshot, master_securities, update_stock_dates
from .eodhd import EodhdAuthError, EodhdRateLimitError, EodhdResponseError, EodhdSource
from .storage import (
    VerificationError,
    build_expected,
    load_trade_date_bounds,
    verify_parquet,
    write_daily_bars,
)

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


def _apply_dates_and_snapshot(conn: psycopg.Connection[TupleRow], base_dir: Path) -> int:
    """후처리(run_bulk·finalize 공통): Parquet bounds → stock 날짜 backfill → 스냅샷 export.

    ⚠️ commit 은 호출부(main/CLI) 소유 — 코어에 commit 넣으면 test rollback 격리가 깨져 라이브
    PG 오염(critic C1). export 는 같은 conn 의 미커밋 backfill 을 read-your-own-writes 로 본다.
    반환 = 스냅샷 종목 수.
    """
    update_stock_dates(conn, load_trade_date_bounds(base_dir))
    return export_stock_snapshot(conn, base_dir)


def _run_verify(base_dir: Path, expected: dict[str, TickerExpectation] | None) -> bool:
    """--verify 무결성 검사(예외 격리) — 실패해도 적재·날짜는 영속(verify 는 보고용·차단 아님).

    ⚠️ verify_parquet 은 대용량(5.1G)에서 ≥수백초·메모리 큼 → 기본 off, S6 전 1회 게이트로만.
    ⚠️ expected 빈(재개·전부 skip) 시 missing/shortfall 게이트 no-op(중복·음수·OHLC 무결성만) —
    S6 완전성은 master/snapshot 에서 expected 도출 필요(M1·범위 밖).
    """
    try:
        report = verify_parquet(base_dir, expected=expected)
    except VerificationError:
        logger.error(
            "Parquet 무결성 검증 실패(--verify) — 적재·날짜는 영속, 데이터 신뢰 전 조사 필요",
            exc_info=True,
        )
        return False
    return report.passed


def run_bulk(
    source: EodhdSource,
    *,
    base_dir: Path,
    conn: psycopg.Connection[TupleRow],
    limit: int | None = None,
    max_retries: int = 3,
    rate_sleep: float = 0.06,
    sleep_fn: Callable[[float], None] = time.sleep,
    verify: bool = False,
) -> dict[str, int]:
    """종목마스터 대상 다년 EOD → Parquet 벌크 + 후처리(날짜 backfill·스냅샷). 반환 = 커버리지 요약.

    재개(체크포인트 done/empty skip·failed 재시도). 후처리=`_apply_dates_and_snapshot`.
    verify=True 면 무결성 1회(예외격리). commit 은 호출부(C1).
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

    # 후처리: 날짜 backfill → 스냅샷 export(commit 은 호출부·C1·verify 는 옵션).
    n_snapshot = _apply_dates_and_snapshot(conn, base_dir)

    total = len(tickers)
    summary = {
        "master": total,
        "fetched": fetched,
        "empty": empty,
        "failed": failed,
        "skipped": skipped,
        "snapshot": n_snapshot,
    }
    if verify:  # --verify 시에만 무결성 검사(off 면 verify_passed 키 없음·M1 계약)
        summary["verify_passed"] = int(_run_verify(base_dir, expected))
    coverage = 100.0 * fetched / total if total else 0.0
    logger.info("벌크 적재 요약: %s · coverage(이번 run fetched/master)=%.1f%%", summary, coverage)
    return summary


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="stockpick.data.bulk")
    parser.add_argument("--limit", type=int, default=None, help="처리 ticker 수 제한(스모크/단계)")
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="적재 루프 skip — 날짜 backfill+스냅샷 export 만(복구·재동기·멱등)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="후처리 후 무결성 검사 1회(대용량 ≥수백초·기본 off·S6 전 게이트용)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """`python -m stockpick.data.bulk [--limit N | --finalize] [--verify]` — 진입점(commit 소유).

    기본: 마스터 대상 다년 EOD 벌크(수시간·재개 가능). `--finalize`: 적재 skip·날짜/스냅샷만(복구).
    ⚠️ 풀백필은 API(uvicorn) 정지 후 격리 컨테이너 권장(full_series 동시 메모리 OOM 회피·CLAUDE.md).
    """
    configure_logging()  # G6 — httpx 토큰 로거 가드
    ns = _parse_args(argv)
    finalize: bool = bool(ns.finalize)
    do_verify: bool = bool(ns.verify)
    limit: int | None = ns.limit
    base_dir = Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))
    conn = connect()
    try:
        if finalize:  # 복구·재동기 — 적재 루프 없이 날짜/스냅샷만(현 29/50,184 → 전체)
            if limit is not None:
                logger.warning("--limit 은 --finalize 와 무관 — 무시(finalize 는 전체 후처리)")
            summary: dict[str, int] = {"snapshot": _apply_dates_and_snapshot(conn, base_dir)}
            if do_verify:
                summary["verify_passed"] = int(_run_verify(base_dir, expected=None))
        else:
            source = EodhdSource()
            summary = run_bulk(source, base_dir=base_dir, conn=conn, limit=limit, verify=do_verify)
        conn.commit()  # ⚠️ commit 은 진입점만(run_bulk/_apply 코어는 commit 안 함·C1)
    finally:
        conn.close()
    print(f"[bulk] {'finalize' if finalize else '벌크 가격 적재'}: {summary}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
