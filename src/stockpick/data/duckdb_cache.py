"""DuckDB 파생 캐시 — Parquet(1차 진실원본) → cache.duckdb 단일 컬럼 table(백테스트 빠른 스캔).

⚠️ ADR-007. `.duckdb` = 파생(재생성·단방향 Parquet→DuckDB·ADR-006 철학). 578k 파일 glob 풀스캔
(30초/회) → 단일 컬럼 스토어로 백테스트 가속. `(ticker,trade_date)` 인덱스는 `=ANY`/window 미사용
(EXPLAIN SEQ_SCAN 실측)이라 안 만듦. 원자 빌드(temp→os.replace). bulk --finalize 재생성·부재 폴백.

모듈 경계(python-conventions): data 층 — duckdb·stdlib 만 의존(상위 rules/backtest import 금지).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    import duckdb

logger = logging.getLogger(__name__)

_DB_NAME = "cache.duckdb"
_TMP_NAME = ".cache.duckdb.tmp"
_TABLE = "daily_bar"
_DATASET = "daily_bar"
_MEMORY_LIMIT = "4GB"  # 적재 OOM 방어(디스크 스필) — app mem_limit 12g 내 여유


def cache_path(base_dir: Path) -> Path:
    return base_dir / _DB_NAME


def cache_exists(base_dir: Path) -> bool:
    return cache_path(base_dir).is_file()


def build_cache(base_dir: Path) -> int:
    """Parquet 트리 → cache.duckdb 단일 table(원자·멱등). 반환=행수. 빈 트리면 0(no-op).

    원자: temp `.duckdb` 빌드 → `os.replace`(반쪽 부패 방지·재시작에도 일관). 중복
    (ticker,trade_date) 발견 시 ValueError(loud fail — 조용한 무결성 위반 금지). 인덱스 없음
    (EXPLAIN SEQ_SCAN·미사용·ADR-007). 멱등: 재실행 시 동일 결과(전량 재생성).
    ⚠️ 빌드 실패 시 기존 cache.duckdb 보존(os.replace 미도달·temp 잔존). Parquet 갱신 후
    실패면 stale 가능 — 호출부(Task4) 폴백/재빌드 책임. memory_limit 충분성 Task7 실측.
    """
    dataset_root = base_dir / _DATASET
    # files=빈 체크용·glob=적재용(동일 트리·storage 패턴 미러·M1).
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        logger.warning("캐시 빌드 대상 Parquet 없음 — skip: %s", dataset_root)
        return 0

    import duckdb

    tmp = base_dir / _TMP_NAME
    for leftover in (tmp, base_dir / (_TMP_NAME + ".wal")):
        if leftover.exists():
            leftover.unlink()  # 이전 실패 잔재 정리

    glob = f"{dataset_root}/**/*.parquet"
    con = duckdb.connect(str(tmp))
    try:
        con.execute(f"SET memory_limit='{_MEMORY_LIMIT}'")
        con.execute("PRAGMA disable_progress_bar")
        con.execute(
            f"CREATE TABLE {_TABLE} AS "  # noqa: S608 — _TABLE 리터럴·glob 파라미터 바인딩
            "SELECT ticker, trade_date, close, adj_factor "
            "FROM read_parquet($glob, hive_partitioning=true)",
            {"glob": glob},
        )
        dup_row = con.execute(
            f"SELECT count(*) FROM (SELECT ticker, trade_date FROM {_TABLE} "  # noqa: S608 — _TABLE 리터럴
            "GROUP BY ticker, trade_date HAVING count(*) > 1)"
        ).fetchone()
        dup_n = int(dup_row[0]) if dup_row else 0
        if dup_n:
            msg = (
                f"중복 (ticker, trade_date) {dup_n}건 — 캐시 빌드 중단"
                "(데이터 무결성 위반·조용한 통과 금지)"
            )
            raise ValueError(msg)
        row = con.execute(f"SELECT count(*) FROM {_TABLE}").fetchone()  # noqa: S608
        n = int(row[0]) if row else 0
    finally:
        con.close()

    os.replace(tmp, cache_path(base_dir))  # 원자 교체
    logger.info("DuckDB 캐시 빌드: %d행 → %s", n, cache_path(base_dir))
    return n


def connect_readonly(base_dir: Path) -> duckdb.DuckDBPyConnection:
    """cache.duckdb read_only 연결(다중 reader 허용·호출부 close 책임). 부재/부패 시 duckdb 예외."""
    import duckdb

    return duckdb.connect(str(cache_path(base_dir)), read_only=True)
