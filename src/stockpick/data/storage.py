"""일봉 저장층 — `list[DailyBar]` → Hive 파티션 Parquet + DuckDB 무결성 검증(M1 §3·§5).

백테스트 1차 진실원본은 Parquet(DuckDB 스캔)이다. 이 모듈은 어댑터(`tiingo` 등)가 뽑은
`list[DailyBar]` 를 거래소·연도 파티션으로 영속화하고, 적재 산출물을 DuckDB 로 다시 스캔해
금융 무결성을 게이트로 검증한다. 모듈 경계(python-conventions): `data` 는 도메인 계약(`..types`)만
의존하며 `rules`/`backtest`/상위를 import 하지 않는다.

⚠️ 정밀도 BLOCKING(M1 §5): 가격·adj_factor 는 pyarrow **decimal128** 로 저장한다 — float64
다운캐스트 금지(부동소수 오차로 수익률 왜곡). DailyBar 의 Decimal 을 손실 없이 옮기되, 컬럼
고정 scale 을 초과하는 정밀도가 들어오면 **조용히 반올림하지 않고 명시적으로 실패**한다.

⚠️ 재현성 BLOCKING(M1 §5): 모든 행에 `source`·`ingested_at` 을 동반한다(동일 입력 재적재 시
재현 가능). 멱등: 같은 (ticker, trade_date) 를 재적재하면 중복 누적 없이 **마지막 적재로 덮어쓴다**
(파티션 디렉토리 단위 재작성 — 아래 write_daily_bars 시맨틱 참조).

⚠️ 생존편향(M1 §5): 폐지 종목도 동일 레이아웃으로 같은 트리에 적재한다(분리 금지 — 스캔 누락 방지).
이 모듈은 ticker 키로만 저장하며, ticker 재사용 구간의 CIK 해소는 백테스트 단계의
ticker_history 책임.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pyarrow as pa
import pyarrow.parquet as pq

if TYPE_CHECKING:
    from collections.abc import Sequence

    from duckdb import DuckDBPyConnection

    from ..types import DailyBar, Exchange

logger = logging.getLogger(__name__)

# decimal128 컬럼 정밀도(precision, scale) — 실측 근거(2026-06-16, 라이브 NVDA 로 보정):
#   - 가격(OHLC): Tiingo raw 는 소수 4자리 수준이나 여유 scale 10. 정수부 28자리(어떤 주가도 수용).
#   - adj_factor = adjClose/close 는 기본 Decimal(prec=28) 나눗셈 결과. factor<1(분할)이면
#     유효숫자 28자리가 선행 0 뒤에 와 scale 이 28 을 넘는다. 라이브 NVDA(10:1)에서
#     scale=29 실측 → 초기 28 가정이 게이트에 걸려 발견(설계대로 조용히 자르지 않고 실패).
#     정수부 1자리 보장 + scale 37(precision 38) 로 상향: 선행 0 9개(factor≈1e-9)까지, 역분할로
#     factor≥1(역분할, 한 자릿수)도 수용. ⚠️ factor 의 28자리 꼬리는 나눗셈 인공물(의미정밀도 아님 —
#     adjClose 가 소수 4자리). factor 산출 정밀도는 본래 어댑터 책임이라 후속 정합 필요(아래 NOTE).
# NOTE(후속): adj_factor 의 무의미한 무한소수 꼬리를 어댑터(_compute_adj_factor)에서 의도된 정밀도로
#   고정(adjClose·close 유효 자릿수 기반 quantize)이 정공법. 저장층은 받은 값을 손실 없이 담을 뿐
#   (조용한 반올림 금지) — scale 상향은 그 계약을 지키는 임시 수용. M2 전 어댑터 정합 권고.
_PRICE_PRECISION: Final = 38
_PRICE_SCALE: Final = 10
_FACTOR_PRECISION: Final = 38
_FACTOR_SCALE: Final = 37

_DATASET_NAME: Final = "daily_bar"
_ZSTD: Final = "zstd"

# 검증 SQL — 골격은 전부 코드 리터럴, 경로는 $glob 파라미터 바인딩(사용자 입력이 SQL 에 안 섞임).
#   S608(f-string SQL injection)은 이 맥락에 해당 없음(리터럴 상수)이라 정당하게 무시.
_FROM: Final = "FROM read_parquet($glob, hive_partitioning=true)"
_SQL_ROW_COUNT: Final = f"SELECT count(*) {_FROM}"  # noqa: S608
_SQL_TICKER_COUNT: Final = f"SELECT count(DISTINCT ticker) {_FROM}"  # noqa: S608
_SQL_MIN_DATE: Final = f"SELECT min(trade_date) {_FROM}"  # noqa: S608
_SQL_MAX_DATE: Final = f"SELECT max(trade_date) {_FROM}"  # noqa: S608
_SQL_DUPLICATES: Final = (
    f"SELECT coalesce(sum(c - 1), 0) FROM ("  # noqa: S608
    f"  SELECT count(*) AS c {_FROM} GROUP BY ticker, trade_date HAVING count(*) > 1"
    f")"
)
_SQL_NONPOSITIVE_ADJ: Final = f"SELECT count(*) {_FROM} WHERE adj_factor <= 0"  # noqa: S608
_SQL_OHLC_VIOLATION: Final = (  # noqa: S608
    f"SELECT count(*) {_FROM} WHERE "
    f"high < low OR high < open OR high < close OR low > open OR low > close"
)


class StorageError(RuntimeError):
    """저장층 기반 예외. 정밀도 초과·검증 게이트 실패 등 데이터 무결성 위협을 명확히 알린다."""


class PrecisionError(StorageError):
    """Decimal 값이 컬럼 고정 scale 을 초과 — 조용한 반올림 대신 명시적 실패(정밀 BLOCKING)."""


class VerificationError(StorageError):
    """DuckDB 검증 게이트 위반(중복·adj_factor<=0·OHLC 부정합). 적재 신뢰 차단."""


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """DuckDB 검증 결과 리포트. passed=False 면 게이트 실패(VerificationError 동반)."""

    row_count: int
    ticker_count: int
    min_date: str | None
    max_date: str | None
    duplicate_count: int
    nonpositive_adj_factor_count: int
    ohlc_violation_count: int

    @property
    def passed(self) -> bool:
        return (
            self.duplicate_count == 0
            and self.nonpositive_adj_factor_count == 0
            and self.ohlc_violation_count == 0
        )


def _arrow_schema() -> pa.Schema:
    """Parquet 스키마. 가격·adj_factor = decimal128(정밀 BLOCKING), volume bigint, value nullable.

    파티션 키(exchange/year)는 Hive 디렉토리로 표현되므로 파일 내부 컬럼에서는 제외(pyarrow dataset
    관례). source/ingested_at 은 재현성 메타로 모든 행에 동반.
    """
    return pa.schema(
        [
            pa.field("ticker", pa.string(), nullable=False),
            pa.field("trade_date", pa.date32(), nullable=False),
            pa.field("open", pa.decimal128(_PRICE_PRECISION, _PRICE_SCALE), nullable=False),
            pa.field("high", pa.decimal128(_PRICE_PRECISION, _PRICE_SCALE), nullable=False),
            pa.field("low", pa.decimal128(_PRICE_PRECISION, _PRICE_SCALE), nullable=False),
            pa.field("close", pa.decimal128(_PRICE_PRECISION, _PRICE_SCALE), nullable=False),
            pa.field("volume", pa.int64(), nullable=False),
            pa.field("value", pa.int64(), nullable=True),
            pa.field(
                "adj_factor",
                pa.decimal128(_FACTOR_PRECISION, _FACTOR_SCALE),
                nullable=False,
            ),
            pa.field("source", pa.string(), nullable=False),
            pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        ]
    )


def _check_scale(value: Decimal, *, scale: int, column: str, ticker: str) -> Decimal:
    """Decimal 소수 자릿수가 컬럼 scale 이내인지 검증. 초과 시 PrecisionError(조용한 반올림 금지).

    pyarrow 는 입력 Decimal scale 이 컬럼 scale 보다 크면 변환 시 예외를 던지긴 하나, 우리가
    어느 컬럼·어느 ticker·어떤 값인지 명확히 보고하기 위해 사전 검사한다(실패 명확 보고 원칙).
    """
    exponent = value.as_tuple().exponent
    # exponent 는 정수(유한 Decimal). 음수 절댓값 = 소수 자릿수.
    if isinstance(exponent, int) and -exponent > scale:
        raise PrecisionError(
            f"Decimal 정밀도 초과: column={column}, ticker={ticker}, "
            f"value_scale={-exponent} > column_scale={scale} (값={value}). "
            "조용한 반올림은 수익률 왜곡(BLOCKING)이라 거부합니다. 컬럼 scale 상향 또는 "
            "입력 정밀도 점검이 필요합니다."
        )
    return value


def _bars_to_table(bars: Sequence[DailyBar], *, source: str, ingested_at: datetime) -> pa.Table:
    """DailyBar 시퀀스 → Arrow Table. Decimal 은 손실 없이 옮기고 scale 초과는 명시적 실패."""
    schema = _arrow_schema()
    cols: dict[str, list[object]] = {f.name: [] for f in schema}
    for bar in bars:
        cols["ticker"].append(bar.ticker)
        cols["trade_date"].append(bar.trade_date)
        for name, raw in (
            ("open", bar.open),
            ("high", bar.high),
            ("low", bar.low),
            ("close", bar.close),
        ):
            cols[name].append(_check_scale(raw, scale=_PRICE_SCALE, column=name, ticker=bar.ticker))
        cols["volume"].append(bar.volume)
        cols["value"].append(bar.value)
        cols["adj_factor"].append(
            _check_scale(
                bar.adj_factor, scale=_FACTOR_SCALE, column="adj_factor", ticker=bar.ticker
            )
        )
        cols["source"].append(source)
        cols["ingested_at"].append(ingested_at)
    return pa.Table.from_pydict(cols, schema=schema)


def write_daily_bars(
    bars: Sequence[DailyBar],
    *,
    exchange: Exchange,
    base_dir: Path,
    source: str,
    ingested_at: datetime | None = None,
) -> Path:
    """`list[DailyBar]` → Hive 파티션 Parquet 적재. 반환 = 적재된 파티션 트리 루트 경로.

    레이아웃(M1 §3): `{base_dir}/daily_bar/exchange={EX}/year={YYYY}/*.parquet`. 파일은
    (ticker, trade_date) 정렬, zstd 압축. DailyBar 엔 exchange 가 없으므로(가격 키는 ticker)
    호출부가 ticker 의 거래소를 인자로 공급한다(파일럿이 ticker→exchange 표 보유).

    멱등(재현성 BLOCKING): 파일을 **(exchange, year) 파티션 안에서 ticker 별로 분리**한다
    (`year={YYYY}/{ticker}.parquet`). 같은 ticker 를 재적재하면 그 ticker 파일만 덮어쓰고, 같은
    파티션의 **다른 ticker 파일은 건드리지 않는다** — ticker 별 적재가 서로의 데이터를 지우지 않게
    한다(라이브 파일럿 실측 회귀: 단일 파티션 파일 방식이면 같은 거래소·연도를 공유하는 이전 ticker
    가 조용히 소실됐고 게이트도 못 잡았다). 빈 입력은 no-op(파일 미생성).

    ⚠️ ingested_at=None 이면 호출 시각(UTC)을 1회 고정해 모든 행에 동일 적용(같은 배치 = 같은 시각).
    """
    dataset_root = base_dir / _DATASET_NAME
    if not bars:
        logger.info("적재할 DailyBar 0건 — no-op: exchange=%s, base_dir=%s", exchange, base_dir)
        return dataset_root

    stamp = ingested_at if ingested_at is not None else datetime.now(UTC)

    # (year, ticker)로 그룹핑 — 파티션 디렉토리(year) × 파일(ticker). pyarrow.compute/dataset 의
    # 동적 export 미타이핑(strict)을 피하려 연도 계산·파티션 쓰기는 Python+pq.write_table 로 직접.
    by_group: dict[tuple[int, str], list[DailyBar]] = {}
    for bar in bars:
        by_group.setdefault((bar.trade_date.year, bar.ticker), []).append(bar)

    total_rows = 0
    for (year, ticker), group_bars in by_group.items():
        table = _bars_to_table(group_bars, source=source, ingested_at=stamp)
        # trade_date 정렬(M1 §3) — 파일 내부 정렬로 스캔·압축 효율(파일당 단일 ticker).
        table = table.sort_by([("trade_date", "ascending")])

        part_dir = dataset_root / f"exchange={exchange}" / f"year={year}"
        part_dir.mkdir(parents=True, exist_ok=True)
        # 멱등: 이 ticker 파일만 덮어쓴다(같은 파티션의 다른 ticker 보존). write_table 은
        # py.typed(partial)에서 untyped — strict no-untyped-call 만 예외(라이브러리 stub 한계).
        target = part_dir / f"{ticker}.parquet"
        pq.write_table(table, str(target), compression=_ZSTD)  # type: ignore[no-untyped-call]
        total_rows += table.num_rows

    logger.info(
        "Parquet 적재 완료: dataset=%s, exchange=%s, rows=%d, files=%d, source=%s",
        dataset_root,
        exchange,
        total_rows,
        len(by_group),
        source,
    )
    return dataset_root


def verify_parquet(base_dir: Path) -> VerificationReport:
    """적재된 Parquet 트리를 DuckDB 로 스캔해 금융 무결성을 게이트로 검증(M1 §5).

    검증 항목:
      (a) 중복 (ticker, trade_date) = 0       — 멱등 위반·이중 적재 탐지
      (b) adj_factor > 0                       — 수정계수 0/음수는 수익률 계산 붕괴
      (c) OHLC 정합: high>=low, high>=open/close, low<=open/close — 가격 무결성
      (d) 리포트: 행수·종목수·기간(min/max trade_date)
    위반이 하나라도 있으면 VerificationError(게이트 실패). 트리가 비면 0행 리포트(passed=True).

    Java 비유: 적재 후 통합 테스트의 어서션 묶음 — repository.saveAll() 직후 select 로 불변식
    (유니크 제약·체크 제약)을 재확인하는 것과 같다. 여기선 DB 제약 대신 Parquet 스캔으로 검사.
    """
    dataset_root = base_dir / _DATASET_NAME
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        logger.warning("검증 대상 Parquet 없음 — 빈 리포트: dataset=%s", dataset_root)
        return VerificationReport(
            row_count=0,
            ticker_count=0,
            min_date=None,
            max_date=None,
            duplicate_count=0,
            nonpositive_adj_factor_count=0,
            ohlc_violation_count=0,
        )

    import duckdb

    # 경로는 $glob 파라미터 바인딩으로만 주입(사용자 입력이 SQL 문자열에 안 섞임). SQL 골격은 위
    # _SQL_* 상수(코드 리터럴)라 injection 불가.
    glob = f"{dataset_root}/**/*.parquet"
    params: dict[str, object] = {"glob": glob}

    con = duckdb.connect(database=":memory:")
    try:
        row_count = _scalar_int(con, _SQL_ROW_COUNT, params)
        ticker_count = _scalar_int(con, _SQL_TICKER_COUNT, params)
        min_date = _scalar_str(con, _SQL_MIN_DATE, params)
        max_date = _scalar_str(con, _SQL_MAX_DATE, params)
        duplicate_count = _scalar_int(con, _SQL_DUPLICATES, params)
        nonpositive_adj = _scalar_int(con, _SQL_NONPOSITIVE_ADJ, params)
        ohlc_violation = _scalar_int(con, _SQL_OHLC_VIOLATION, params)
    finally:
        con.close()

    report = VerificationReport(
        row_count=row_count,
        ticker_count=ticker_count,
        min_date=min_date,
        max_date=max_date,
        duplicate_count=duplicate_count,
        nonpositive_adj_factor_count=nonpositive_adj,
        ohlc_violation_count=ohlc_violation,
    )
    logger.info(
        "Parquet 검증: rows=%d, tickers=%d, period=%s~%s, dup=%d, adj<=0=%d, ohlc=%d, passed=%s",
        report.row_count,
        report.ticker_count,
        report.min_date,
        report.max_date,
        report.duplicate_count,
        report.nonpositive_adj_factor_count,
        report.ohlc_violation_count,
        report.passed,
    )
    if not report.passed:
        raise VerificationError(
            "Parquet 무결성 게이트 실패(금융 BLOCKING): "
            f"중복={report.duplicate_count}, adj_factor<=0={report.nonpositive_adj_factor_count}, "
            f"OHLC위반={report.ohlc_violation_count}. 적재 데이터를 신뢰할 수 없습니다."
        )
    return report


def _scalar_int(con: DuckDBPyConnection, sql: str, params: dict[str, object]) -> int:
    """DuckDB 단일 정수 스칼라. None(빈 결과)은 0 으로 환원(count 계열)."""
    row = con.execute(sql, params).fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def _scalar_str(con: DuckDBPyConnection, sql: str, params: dict[str, object]) -> str | None:
    """DuckDB 단일 문자열 스칼라(날짜 등). None 허용."""
    row = con.execute(sql, params).fetchone()
    if row is None or row[0] is None:
        return None
    return str(row[0])
