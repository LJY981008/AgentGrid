"""A-1 데이터 정제 — EODHD 0-OHLCV·OHLC 순서위반 봉을 `normalize_ohlc` 로 정제(영향 파일만 재작성).

`verify_parquet`(G-7) 블로커 해소. DuckDB 로 결함 보유 (exchange,year,ticker) 파일만 식별 → pyarrow
로 그 파일만 재작성(close<=0 drop·순서 close anchor 보정). 정규화는 ingest(`_row_to_bar`)와 **동일
함수**(`storage.normalize_ohlc`) — ingest·정제 동형 보장. 원자(temp+os.replace)·결정적·멱등.

모듈 경계(python-conventions): data 층 — pyarrow/duckdb/stdlib·`storage` 만. 일회성 운영 도구이나
재실행 안전(정상 봉 멱등). 실행 후 `build_cache` 재빌드 필요(cache.duckdb 는 Parquet 파생).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .storage import normalize_ohlc

logger = logging.getLogger(__name__)

_DATASET = "daily_bar"
# 결함 술어 — verify_parquet 와 **정확히 동형**(nonpositive 4항 + OHLC ordering 5항). ⚠️ close<=0
# 만으론 low<=0(ordering OK) 등 nonpositive 가 누락돼 영향 파일을 못 잡는다(verify 여전히 FAIL).
_DEFECT_SQL = (
    "open<=0 OR high<=0 OR low<=0 OR close<=0 "
    "OR high<low OR high<open OR high<close OR low>open OR low>close"
)


@dataclass(frozen=True, slots=True)
class CleanReport:
    """정제 결과 — 대상/재작성/비움(전부 drop) 파일 수, 누적 drop/clamp 행 수."""

    files_targeted: int
    files_rewritten: int
    files_emptied: int
    rows_dropped: int
    rows_clamped: int


def _affected_keys(base_dir: Path) -> list[tuple[str, int, str]]:
    """결함 행 보유 (exchange, year, ticker) 목록 — DuckDB 한 번에 식별(전량 스캔 회피용 타겟)."""
    import duckdb

    glob = f"{base_dir / _DATASET}/**/*.parquet"
    con = duckdb.connect(database=":memory:", config={"memory_limit": "4GB"})
    try:
        con.execute("PRAGMA disable_progress_bar")
        con.execute("SET temp_directory=$tmp", {"tmp": str(base_dir)})
        rows = con.execute(
            "SELECT DISTINCT exchange, year(trade_date) AS yr, ticker "  # noqa: S608 — 술어 리터럴
            f"FROM read_parquet($g, hive_partitioning=true) WHERE {_DEFECT_SQL}",
            {"g": glob},
        ).fetchall()
    finally:
        con.close()
    return [(str(ex), int(yr), str(tk)) for ex, yr, tk in rows]


def _clean_file(path: Path) -> tuple[int, int, bool]:
    """파일 1개 정제 → (dropped, clamped, emptied). 원자 재작성. 전부 drop 이면 파일 삭제.

    파티션 컬럼(exchange/year)은 파일에 없어야 정상(Hive 디렉토리) — 혹시 포함돼 읽히면 제외하고
    데이터 컬럼만 보존(파일에 파티션 컬럼 재기입 금지). close 불변·open/high/low 만 정규화.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pq.ParquetFile(str(path)).read()  # type: ignore[no-untyped-call]
    data_cols = [c for c in table.column_names if c not in ("exchange", "year")]
    cols = {name: table.column(name).to_pylist() for name in data_cols}
    n = table.num_rows
    out: dict[str, list[object]] = {name: [] for name in data_cols}
    dropped = clamped = 0
    for i in range(n):
        result = normalize_ohlc(cols["open"][i], cols["high"][i], cols["low"][i], cols["close"][i])
        if result is None:
            dropped += 1
            continue
        op, hi, lo, _close = result
        if (op, hi, lo) != (cols["open"][i], cols["high"][i], cols["low"][i]):
            clamped += 1
        for name in data_cols:
            if name == "open":
                out[name].append(op)
            elif name == "high":
                out[name].append(hi)
            elif name == "low":
                out[name].append(lo)
            else:
                out[name].append(cols[name][i])

    if not out["ticker"]:  # 전부 비거래일(close<=0) → 파일 삭제(빈 파일 잔존 금지)
        path.unlink()
        return dropped, clamped, True

    schema = pa.schema([table.schema.field(c) for c in data_cols])
    new_table = pa.table(out, schema=schema)
    tmp = path.with_name(path.name + ".tmp")
    pq.write_table(new_table, str(tmp), compression="zstd")  # type: ignore[no-untyped-call]
    os.replace(tmp, path)
    return dropped, clamped, False


def clean_parquet_ohlc(base_dir: Path) -> CleanReport:
    """결함 보유 파일만 정제(`normalize_ohlc`). 반환 = 통계. 정상 봉 멱등(재실행 안전)."""
    keys = _affected_keys(base_dir)
    logger.info("A-1 OHLC 정제 대상: %d 파일", len(keys))
    rewritten = emptied = drops = clamps = 0
    dataset_root = base_dir / _DATASET
    for idx, (ex, yr, tk) in enumerate(keys, start=1):
        path = dataset_root / f"exchange={ex}" / f"year={yr}" / f"{tk}.parquet"
        if not path.is_file():
            logger.warning("정제 대상 파일 부재(skip): %s", path)
            continue
        d, c, em = _clean_file(path)
        drops += d
        clamps += c
        if em:
            emptied += 1
        else:
            rewritten += 1
        if idx % 2000 == 0:
            logger.info("정제 진행: %d/%d", idx, len(keys))

    report = CleanReport(len(keys), rewritten, emptied, drops, clamps)
    logger.info(
        "A-1 OHLC 정제 완료: targeted=%d rewritten=%d emptied=%d dropped=%d clamped=%d",
        report.files_targeted,
        report.files_rewritten,
        report.files_emptied,
        report.rows_dropped,
        report.rows_clamped,
    )
    return report


def main() -> int:
    """CLI — `python -m stockpick.data.clean_ohlc`. base_dir=STOCKPICK_DATA_DIR(기본 data/parquet).

    ⚠️ 정제 후 `build_cache`(cache.duckdb 재빌드) + `verify_parquet`(G-7 PASS 확인) 별도 실행.
    """
    from . import configure_logging

    configure_logging()
    base_dir = Path(os.environ.get("STOCKPICK_DATA_DIR", "data/parquet"))
    report = clean_parquet_ohlc(base_dir)
    print(f"[clean_ohlc] {report}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
