"""DuckDB 파생 캐시 — Parquet(1차 진실원본) → cache.duckdb 단일 컬럼 table(백테스트 빠른 스캔).

⚠️ ADR-007. `.duckdb` = 파생(재생성·단방향 Parquet→DuckDB·ADR-006 철학). 578k 파일 glob 풀스캔
(30초/회) → 단일 컬럼 스토어로 백테스트 가속. `(ticker,trade_date)` 인덱스는 `=ANY`/window 미사용
(EXPLAIN SEQ_SCAN 실측)이라 안 만듦. 원자 빌드(temp→os.replace). bulk --finalize 재생성·부재 폴백.

모듈 경계(python-conventions): data 층 — duckdb·stdlib 만 의존(상위 rules/backtest import 금지).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date
    from decimal import Decimal
    from pathlib import Path

    import duckdb

logger = logging.getLogger(__name__)

_DB_NAME = "cache.duckdb"
_TMP_NAME = ".cache.duckdb.tmp"
_TABLE = "daily_bar"
_DATASET = "daily_bar"
_FINANCIAL_TABLE = "financial_fact"  # A3 — 재무 fact 동봉 table(B ROE/PB 푸시다운)
_FINANCIAL_DATASET = "financial_fact"
_MEMORY_LIMIT = "4GB"  # 적재 OOM 방어(디스크 스필) — app mem_limit 12g 내 여유
# 읽기 연결 버퍼풀 캡(ADR-008 후속) — memory_limit 미설정 시 DuckDB 기본=호스트RAM 80%라 다년
# 백테스트 반복 window 쿼리서 버퍼풀이 ~12.8GB 까지 ballooning(profiler 실측: rss 12.8GB vs python
# 0.36GB=native). 캡으로 peak 바운드(초과분 디스크 spill·결과 불변). env 로 튜닝.
_READ_MEMORY_LIMIT = os.environ.get("STOCKPICK_DUCKDB_MEMORY_LIMIT", "6GB")


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
            # volume 추가(ADR-010 유동성 ADV용). momentum_endpoints/load_range 는 volume 미참조
            # → momentum bit-identical 불변(컬럼 존재만·읽지 않음).
            "SELECT ticker, trade_date, close, adj_factor, volume "
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
        # A3: 재무 fact table 동봉(있을 때만 — 백필 전 skip). 평면 financial_fact/<CIK>.parquet.
        # B 의 DuckDB ROE/PB 푸시다운 입력. daily_bar 와 같은 연결 = 원자 동봉.
        fin_root = base_dir / _FINANCIAL_DATASET
        fin_files = sorted(str(p) for p in fin_root.glob("*.parquet"))
        if fin_files:
            con.execute(
                f"CREATE TABLE {_FINANCIAL_TABLE} AS "  # noqa: S608 — 리터럴·glob 파라미터 바인딩
                "SELECT cik, concept, fiscal_period, period_start, period_end, disclosed_at, value "
                "FROM read_parquet($fin_glob)",
                {"fin_glob": f"{fin_root}/*.parquet"},
            )
            logger.info("DuckDB 캐시: financial_fact table 동봉(%d cik 파일)", len(fin_files))
        row = con.execute(f"SELECT count(*) FROM {_TABLE}").fetchone()  # noqa: S608
        n = int(row[0]) if row else 0
    finally:
        con.close()

    os.replace(tmp, cache_path(base_dir))  # 원자 교체
    logger.info("DuckDB 캐시 빌드: %d행 → %s", n, cache_path(base_dir))
    return n


def connect_readonly(base_dir: Path) -> duckdb.DuckDBPyConnection:
    """cache.duckdb read_only 연결(다중 reader·호출부 close 책임). 부재/부패 시 duckdb 예외.

    memory_limit(`_READ_MEMORY_LIMIT`) 캡 — 버퍼풀 ballooning 방지(peak 바운드·초과 디스크 spill·
    결과 불변·ADR-008 후속). 다중 reader 환경에서 합산 메모리도 캡으로 예측 가능.
    """
    import duckdb

    return duckdb.connect(
        str(cache_path(base_dir)), read_only=True, config={"memory_limit": _READ_MEMORY_LIMIT}
    )


@dataclass(frozen=True, slots=True)
class MomentumEndpoints:
    """momentum 부분 푸시다운 raw 끝점(ADR-007). **윈도우** eligible([lo,as_of]·ASC) 0-based idx.

    data 층이라 PricePoint(rules) 미반환 — adjusted/date raw 만(backtest 가 조립·
    momentum_from_endpoints 로 MomentumScore 산출). end/start 둘 중 None 이면 산출 불가(2점미만).
    idx 는 엔진 windowed momentum(load_range·_window_start) 과 동치 — 윈도우 count(wn) 기준.
    """

    end_adjusted: Decimal | None
    end_date: date | None
    start_adjusted: Decimal | None
    start_date: date | None
    end_idx: int  # 윈도우 0-based(=wn-1-skip)
    start_idx: int  # 윈도우 0-based(=max(0, end_idx-lookback))


def momentum_endpoints(
    con: duckdb.DuckDBPyConnection,
    *,
    tickers: Iterable[str],
    as_of: date,
    lookback_days: int,
    skip_recent_days: int,
    window_days: int,
) -> dict[str, MomentumEndpoints]:
    """ticker별 momentum 끝점 — 엔진 windowed momentum(engine._rank_at) 과 **bit-identical**.

    엔진 메모리 경로는 `load_range(tradable, _window_start(t), t)` 로 **윈도우만** 로드해
    momentum_universe 에 넘긴다(window_days=(lookback+skip)*2+30·여유가 lookback+skip 거래일 덮음·
    윈도우 봉 0 종목은 스테일 배제=결과 제외). 이 함수는 그 windowed momentum 을 SQL 로 재현 —
    **윈도우가 곧 eligible 집합**이라 전체 tot 가 아니라 윈도우 count(wn) 기준으로 산출한다.

    DESC rd: e1=skip+1(end)·e2=skip+lookback+1(start). graceful(wn<=e2)면 start=윈도우 최古(rd=wn).
    bit-identical 핵심: `close*adj_factor` DECIMAL 곱·**나눗셈은 Python**(momentum_from_endpoints).
    룩어헤드: `trade_date BETWEEN $lo AND $as_of`(상한=as_of). 윈도우 봉 0 ticker 는 결과에서 제외
    (load_range.setdefault 와 동일 — 행 있는 ticker 만 생성).
    """
    tk = list(tickers)
    if not tk:
        return {}
    lo = as_of - timedelta(days=window_days)
    e1 = skip_recent_days + 1  # end DESC rd
    e2 = skip_recent_days + lookback_days + 1  # start DESC rd(non-graceful)
    sql = (
        "WITH w AS (SELECT ticker, close*adj_factor adj, trade_date td, "  # noqa: S608 — daily_bar 리터럴·바인딩
        "ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) rd, "
        "COUNT(*) OVER (PARTITION BY ticker) wn FROM daily_bar "
        "WHERE ticker = ANY($t) AND trade_date BETWEEN $lo AND $a) "
        "SELECT ticker, adj, td, rd, wn FROM w WHERE rd IN ($e1, $e2) OR rd = wn"
    )
    rows = con.execute(sql, {"t": tk, "a": as_of, "lo": lo, "e1": e1, "e2": e2}).fetchall()
    grouped = _group_window_rows(rows)
    out: dict[str, MomentumEndpoints] = {}
    for ticker, (rdmap, wn) in grouped.items():
        end_idx = wn - 1 - skip_recent_days  # 윈도우 0-based(load_range eligible 끝)
        start_idx = max(0, end_idx - lookback_days)
        end = rdmap.get(e1)
        if end_idx < 1 or end is None:  # 2점미만 — momentum(windowed) None 과 동치
            out[ticker] = MomentumEndpoints(None, None, None, None, end_idx, start_idx)
            continue
        # graceful(wn<=e2·start_idx==0)면 윈도우 최古(rd=wn), 아니면 e2(둘 다 윈도우 내 존재 보장).
        start = rdmap.get(wn) if wn <= e2 else rdmap.get(e2)
        out[ticker] = MomentumEndpoints(
            end[0],
            end[1],
            start[0] if start is not None else None,
            start[1] if start is not None else None,
            end_idx,
            start_idx,
        )
    return out


def query_liquid_tickers(
    con: duckdb.DuckDBPyConnection,
    *,
    as_of: date,
    candidates: Iterable[str],
    min_price: Decimal,
    min_adv: Decimal,
    window: int,
) -> set[str]:
    """ADR-010 PIT 유동성 필터 — candidates 중 as_of 시점 유동/가격 충족 ticker 집합(단일 SQL 출처).

    각 ticker 의 `trade_date ≤ as_of` 최근 `window` 거래일로: ADV=mean(close×volume) ≥ min_adv
    AND 최근 close(arg_max by trade_date) ≥ min_price. 봉 < window(신규/희박)면 제외(보수).
    룩어헤드: 상한=as_of(이후 0). $lo 는 window 거래일을 덮는 여유·비유동은 count 미달 제외.
    backtest 포트(adapters)·api(ranking) 공유 — engine·벤치 대칭 동일 SQL.
    """
    tk = list(candidates)
    if not tk:
        return set()
    lo = as_of - timedelta(days=window * 3 + 7)  # window 거래일 충분 포함(여유)
    sql = (
        "WITH w AS (SELECT ticker, close, close*volume dvol, trade_date, "  # noqa: S608 — daily_bar 리터럴·바인딩
        "ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) rd "
        "FROM daily_bar WHERE ticker = ANY($t) AND trade_date BETWEEN $lo AND $a) "
        "SELECT ticker FROM w WHERE rd <= $win GROUP BY ticker "
        "HAVING count(*) >= $win AND avg(dvol) >= $minadv "
        "AND arg_max(close, trade_date) >= $minprice"
    )
    rows = con.execute(
        sql,
        {"t": tk, "a": as_of, "lo": lo, "win": window, "minadv": min_adv, "minprice": min_price},
    ).fetchall()
    return {r[0] for r in rows if isinstance(r[0], str)}


def _group_window_rows(
    rows: list[tuple[object, ...]],
) -> dict[str, tuple[dict[int, tuple[Decimal, date]], int]]:
    """윈도우 SQL 행 → {ticker: ({rd: (adj, td)}, wn)} (타입 narrowing·실패 명확 보고).

    wn=윈도우 count(파티션 상수 — 첫 행에서 캡처). rd 별 (adjusted, trade_date) 맵.
    """
    from datetime import date as date_cls
    from decimal import Decimal as decimal_cls

    grouped: dict[str, tuple[dict[int, tuple[Decimal, date]], int]] = {}
    for row in rows:
        ticker, adj, td, rd, wn = row
        if not (
            isinstance(ticker, str)
            and isinstance(adj, decimal_cls)
            and isinstance(td, date_cls)
            and isinstance(rd, int)
            and isinstance(wn, int)
        ):
            msg = f"예상치 못한 momentum 끝점 행 타입: {[type(x).__name__ for x in row]}"
            raise TypeError(msg)
        rdmap = grouped.setdefault(ticker, ({}, wn))[0]
        rdmap[rd] = (adj, td)
    return grouped
