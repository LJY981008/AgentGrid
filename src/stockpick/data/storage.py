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
import os
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
#   - 가격(OHLC): Tiingo/EODHD raw 는 소수 4자리 수준이나 여유 scale 10. 정수부 28자리(어떤 주가도
#     수용).
#   - adj_factor: 어댑터 공유 헬퍼(_adjust.compute_adj_factor)가 산출 시 **의도 정밀도 소수 12자리로
#     quantize** 한다(TASK-C). 따라서 컬럼 scale 도 12 로 맞춘다 — 헬퍼가 고정한 정밀도와 동일해야
#     PrecisionError 없이 손실 없이 적재된다. 정수부 26자리 여유(precision 38) 로 역분할(factor
#     한·두 자릿수)도 수용.
# 이력(TASK-C 이전): adj_factor = adjClose/close 가 기본 Decimal(prec=28) 나눗셈 결과라 factor<1
#   (분할)이면 선행 0 뒤 유효숫자가 와 scale 이 28~29 까지 갔다(라이브 NVDA 10:1 에서 scale 29 실측,
#   게이트가 조용히 자르지 않고 PrecisionError 로 발견). 당시 scale 37 로 상향해 임시 수용했으나, 그
#   꼬리는 나눗셈 인공물(의미정밀도 아님 — adjClose 가 소수 4자리)이었다. TASK-C 에서 산출 단계
#   quantize(12자리)로 근본 해소 → scale 37→12 축소. 헬퍼의 ADJ_FACTOR_DECIMAL_PLACES 와 동일.
_PRICE_PRECISION: Final = 38
_PRICE_SCALE: Final = 10
_FACTOR_PRECISION: Final = 38
_FACTOR_SCALE: Final = 12

_DATASET_NAME: Final = "daily_bar"
_ZSTD: Final = "zstd"

# 검증 SQL — 골격은 전부 코드 리터럴, 경로는 $glob 파라미터 바인딩(사용자 입력이 SQL 에 안 섞임).
#   S608(f-string SQL injection)은 이 맥락에 해당 없음(리터럴 상수)이라 정당하게 무시.
_FROM: Final = "FROM read_parquet($glob, hive_partitioning=true)"
_SQL_ROW_COUNT: Final = f"SELECT count(*) {_FROM}"  # noqa: S608
_SQL_TICKER_COUNT: Final = f"SELECT count(DISTINCT ticker) {_FROM}"  # noqa: S608
_SQL_MIN_DATE: Final = f"SELECT min(trade_date) {_FROM}"  # noqa: S608
_SQL_MAX_DATE: Final = f"SELECT max(trade_date) {_FROM}"  # noqa: S608
# 중복은 파일이 (ticker, year)로 분리돼 한 파일 안에선 드물고, glob 으로 모든 파일을 가로질러
# union 스캔할 때만(예: 같은 ticker·연도가 두 파일로 쪼개진 비정상 적재) 의미가 있다.
_SQL_DUPLICATES: Final = (
    f"SELECT coalesce(sum(c - 1), 0) FROM ("  # noqa: S608
    f"  SELECT count(*) AS c {_FROM} GROUP BY ticker, trade_date HAVING count(*) > 1"
    f")"
)
_SQL_NONPOSITIVE_ADJ: Final = f"SELECT count(*) {_FROM} WHERE adj_factor <= 0"  # noqa: S608
# 양수성 게이트(금융 BLOCKING): 미국 EOD 에 정당한 음수/0 OHLC 는 없다. 기존 _SQL_OHLC_VIOLATION 은
# high>=low 등 *상대* 관계만 봐 OHLC 가 전부 음수여도 통과했다 — 절대 음수/0 가격을 별도로 차단한다.
_SQL_NONPOSITIVE_PRICE: Final = (  # noqa: S608
    f"SELECT count(*) {_FROM} WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0"
)
_SQL_OHLC_VIOLATION: Final = (  # noqa: S608
    f"SELECT count(*) {_FROM} WHERE "
    f"high < low OR high < open OR high < close OR low > open OR low > close"
)
# ticker별 실제 적재 행수 — expected(기대) 와 대조해 누락·행수 미달(생존편향 소실)을 탐지.
_SQL_TICKER_ROW_COUNTS: Final = f"SELECT ticker, count(*) {_FROM} GROUP BY ticker"  # noqa: S608
# DISTINCT ticker 정렬 — EDGAR 재무 적재가 "가격 보유 종목"만 companyfacts 받도록(SEC 호출 최소).
_SQL_DISTINCT_TICKERS: Final = f"SELECT DISTINCT ticker {_FROM} ORDER BY ticker"  # noqa: S608


class StorageError(RuntimeError):
    """저장층 기반 예외. 정밀도 초과·검증 게이트 실패 등 데이터 무결성 위협을 명확히 알린다."""


class PrecisionError(StorageError):
    """Decimal 값이 컬럼 고정 scale 을 초과 — 조용한 반올림 대신 명시적 실패(정밀 BLOCKING)."""


class VerificationError(StorageError):
    """DuckDB 검증 게이트 위반(중복·adj_factor<=0·음수/0 가격·OHLC 부정합·기대 종목 소실).

    적재 신뢰 차단 — 게이트가 하나라도 위반되면 적재 데이터를 신뢰할 수 없다.
    """


@dataclass(frozen=True, slots=True)
class TickerExpectation:
    """ticker 1건의 기대 적재량. row_count=0 도 명시 기록(추측 채움 금지 — 빈 결과도 기대값).

    ⚠️ 생존편향 BLOCKING(M1 §5): "무엇이 적재되어야 하는가"를 코드가 보유한다. 적재 후 실제
    Parquet 행수가 이보다 적으면(누락·소실) 게이트가 시끄럽게 실패한다. row_count 는 write 직전
    in-memory `list[DailyBar]` 의 (ticker 기준) 행수 — 어댑터가 뽑은 실측치이지 추정이 아니다.
    """

    ticker: str
    row_count: int


def build_expected(bars: Sequence[DailyBar]) -> dict[str, TickerExpectation]:
    """write 직전 in-memory `list[DailyBar]` → ticker별 기대 적재량 맵(소실 탐지 기준값).

    같은 입력을 write_daily_bars 와 verify_parquet 양쪽에 흘려 "기대(expected) vs 실제(actual)"
    를 대조하기 위한 포착 헬퍼. 빈 입력이면 빈 맵(no-op 적재와 정합). ticker 별 행수를 정확히
    센다(중복 trade_date 가 입력에 있으면 그 행수까지 기대에 포함 — 멱등 덮어쓰기는 write 책임).
    """
    expected: dict[str, int] = {}
    for bar in bars:
        expected[bar.ticker] = expected.get(bar.ticker, 0) + 1
    return {t: TickerExpectation(ticker=t, row_count=n) for t, n in expected.items()}


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """DuckDB 검증 결과 리포트. passed=False 면 게이트 실패(VerificationError 동반).

    expected 대조(생존편향 가드)는 verify_parquet 에 expected 를 넘긴 경우만 채워진다:
      - missing_tickers: 기대에 있는데 Parquet 에 0행(조용한 소실 — BLOCKING 실패)
      - shortfall_tickers: {ticker: (expected, actual)} 기대보다 실제 행수가 적음(부분 소실 — 실패)
      - orphan_tickers: 기대에 없는데 Parquet 에 존재(추가 데이터 — 경고만, fail 아님)
    expected 미전달이면 세 집합 모두 비어 있고 expected_checked=False(대조 안 함 — 옛 약점 잔존).
    """

    row_count: int
    ticker_count: int
    min_date: str | None
    max_date: str | None
    duplicate_count: int
    nonpositive_adj_factor_count: int
    nonpositive_price_count: int
    ohlc_violation_count: int
    expected_checked: bool = False
    missing_tickers: tuple[str, ...] = ()
    shortfall_tickers: tuple[tuple[str, int, int], ...] = ()  # (ticker, expected, actual)
    orphan_tickers: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        # orphan 은 정합 위반이 아니라 경고(추가 데이터일 뿐) — passed 에 포함하지 않는다.
        return (
            self.duplicate_count == 0
            and self.nonpositive_adj_factor_count == 0
            and self.nonpositive_price_count == 0
            and self.ohlc_violation_count == 0
            and not self.missing_tickers
            and not self.shortfall_tickers
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


def _merge_existing(target: Path, new_table: pa.Table) -> pa.Table:
    """기존 (ticker,year) 파일 있으면 신규와 병합 — 같은 trade_date 는 **신규 우선**(G1 소실 봉인).

    다년 증분 적재는 같은 (ticker,year)를 여러 호출로 나눠 쓰므로(연도분할), 통째 덮어쓰기는 이전
    행을 소실시킨다. 기존 파일을 읽어 **신규에 없는 trade_date 만** 보존하고 신규를 덧붙인다(같은
    날짜 충돌은 신규 값 우선 — adj_factor 정정 등 최신값 반영, stale 방지). 파일 없으면 신규 그대로.
    파일당 단일 ticker 라 trade_date 만으로 dedup 충분.
    """
    if not target.exists():
        return new_table
    # read_table 은 py.typed(partial)에서 untyped — strict no-untyped-call 만 예외(stub 한계).
    # ⚠️ Hive 경로(exchange=/year=)에서 읽으면 파티션 컬럼이 덧붙고 필드도 nullable 로 와
    # new_table(11컬럼·not-null)과 불일치 → 데이터 컬럼만 select 후 new_table.schema 로 cast
    # (데이터에 null 없으므로 안전).
    old_raw = pq.read_table(str(target))  # type: ignore[no-untyped-call]
    old_table: pa.Table = old_raw.select(new_table.column_names).cast(new_table.schema)
    new_dates = set(new_table.column("trade_date").to_pylist())
    keep_mask = [d not in new_dates for d in old_table.column("trade_date").to_pylist()]
    old_keep = old_table.filter(pa.array(keep_mask))
    return pa.concat_tables([old_keep, new_table])


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

    ⚠️ read-merge-write (S5-a·G1 — 다년 증분 소실 봉인): 기존 `{ticker}.parquet` 가 있으면 **읽어
    신규와 병합**한 뒤 쓴다(통째 덮어쓰기 아님). 같은 (ticker, trade_date) 충돌은 **신규 값 우선**
    (adj_factor 정정 등 최신값 반영). 따라서 같은 ticker·연도를 연도분할 호출로 나눠 넘겨도(1월분
    호출 → 2월분만 호출) 이전 행이 보존된다(다년 적재는 본질적으로 연도분할 호출이라 BLOCKING).
    쓰기는 temp 파일 → `os.replace`(atomic rename)로 중간 실패 시 기존 파일을 보존한다.

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
        new_table = _bars_to_table(group_bars, source=source, ingested_at=stamp)
        part_dir = dataset_root / f"exchange={exchange}" / f"year={year}"
        part_dir.mkdir(parents=True, exist_ok=True)
        target = part_dir / f"{ticker}.parquet"
        # read-merge-write(G1) — 기존 파일과 병합(신규 우선)·소실 봉인. 파일당 단일 ticker 이므로
        # 같은 파티션의 다른 ticker 파일은 무관(보존).
        merged = _merge_existing(target, new_table)
        # trade_date 정렬(M1 §3) — 파일 내부 정렬로 스캔·압축 효율.
        merged = merged.sort_by([("trade_date", "ascending")])
        # atomic: temp(같은 디렉토리=동일 fs) write → os.replace. 중간 실패 시 기존 파일 보존.
        # write_table 은 py.typed(partial)에서 untyped — strict no-untyped-call 만 예외.
        tmp = part_dir / f"{ticker}.parquet.tmp"
        pq.write_table(merged, str(tmp), compression=_ZSTD)  # type: ignore[no-untyped-call]
        os.replace(tmp, target)
        total_rows += merged.num_rows

    logger.info(
        "Parquet 적재 완료: dataset=%s, exchange=%s, rows=%d, files=%d, source=%s",
        dataset_root,
        exchange,
        total_rows,
        len(by_group),
        source,
    )
    return dataset_root


def verify_parquet(
    base_dir: Path,
    *,
    expected: dict[str, TickerExpectation] | None = None,
) -> VerificationReport:
    """적재된 Parquet 트리를 DuckDB 로 스캔해 금융 무결성을 게이트로 검증(M1 §5).

    검증 항목:
      (a) 중복 (ticker, trade_date) = 0       — 멱등 위반·이중 적재 탐지
      (b) adj_factor > 0                       — 수정계수 0/음수는 수익률 계산 붕괴
      (c) 가격 양수성: open/high/low/close > 0 — 미국 EOD 에 정당한 음수/0 가격 없음(c'의 상대
          관계 게이트는 전부 음수여도 통과 → 절대 음수/0 를 별도 차단)
      (c') OHLC 정합: high>=low, high>=open/close, low<=open/close — 가격 상대 무결성
      (d) ⭐ expected 대조(생존편향 BLOCKING): expected 를 주면 ticker별 기대 행수 vs 실제 행수를
          대조해 **누락(missing)·행수 미달(shortfall)** 을 시끄럽게 실패시킨다. orphan(기대에
          없는데 존재)은 경고만. expected=None 이면 이 대조를 건너뛴다(옛 약점 — 호출부가 expected
          를 넘겨야 소실을 탐지).
      (e) 리포트: 행수·종목수·기간(min/max trade_date)
    위반이 하나라도 있으면 VerificationError(게이트 실패). 트리가 비어도 expected 가 비어있지
    않으면 전부 missing 으로 실패한다(전량 소실 = 가장 위험한 케이스).

    ⚠️ 이 expected 대조는 라이브 파일럿 회귀(같은 파티션의 이전 ticker 가 조용히 소실됐는데 게이트가
    "현재 트리"만 봐 PASS 한 버그)를 봉인하는 핵심 가드다. 게이트가 "무엇이 있어야 하는가"를 알아야
    누락을 잡는다(M1 §5 생존편향: 미확보분 정량 고지).

    Java 비유: 적재 후 통합 테스트의 어서션 묶음 — repository.saveAll() 직후 select count 로 저장
    예상 건수(expected)와 실제 건수를 대조하는 것과 같다. DB 제약 대신 Parquet 스캔으로 검사.
    """
    dataset_root = base_dir / _DATASET_NAME
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        # 빈 트리: expected 가 있으면 전량 소실(전부 missing) — passed=False. 없으면 0행 PASS.
        missing = tuple(sorted(expected)) if expected else ()
        if missing:
            logger.error(
                "검증 대상 Parquet 없음인데 기대 종목 %d개 존재 — 전량 소실(BLOCKING): %s",
                len(missing),
                ", ".join(missing),
            )
        else:
            logger.warning("검증 대상 Parquet 없음 — 빈 리포트: dataset=%s", dataset_root)
        report = VerificationReport(
            row_count=0,
            ticker_count=0,
            min_date=None,
            max_date=None,
            duplicate_count=0,
            nonpositive_adj_factor_count=0,
            nonpositive_price_count=0,
            ohlc_violation_count=0,
            expected_checked=expected is not None,
            missing_tickers=missing,
        )
        if not report.passed:
            _raise_verification_error(report)
        return report

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
        nonpositive_price = _scalar_int(con, _SQL_NONPOSITIVE_PRICE, params)
        ohlc_violation = _scalar_int(con, _SQL_OHLC_VIOLATION, params)
        actual_counts = _ticker_row_counts(con, _SQL_TICKER_ROW_COUNTS, params)
    finally:
        con.close()

    missing, shortfall, orphan = _diff_expected(expected, actual_counts)

    report = VerificationReport(
        row_count=row_count,
        ticker_count=ticker_count,
        min_date=min_date,
        max_date=max_date,
        duplicate_count=duplicate_count,
        nonpositive_adj_factor_count=nonpositive_adj,
        nonpositive_price_count=nonpositive_price,
        ohlc_violation_count=ohlc_violation,
        expected_checked=expected is not None,
        missing_tickers=missing,
        shortfall_tickers=shortfall,
        orphan_tickers=orphan,
    )
    logger.info(
        "Parquet 검증: rows=%d, tickers=%d, period=%s~%s, dup=%d, adj<=0=%d, price<=0=%d, ohlc=%d, "
        "expected_checked=%s, missing=%d, shortfall=%d, orphan=%d, passed=%s",
        report.row_count,
        report.ticker_count,
        report.min_date,
        report.max_date,
        report.duplicate_count,
        report.nonpositive_adj_factor_count,
        report.nonpositive_price_count,
        report.ohlc_violation_count,
        report.expected_checked,
        len(report.missing_tickers),
        len(report.shortfall_tickers),
        len(report.orphan_tickers),
        report.passed,
    )
    # orphan 은 fail 아님(추가 데이터) — 그러나 기대와 어긋난 신호이므로 경고로 시끄럽게 남긴다.
    if report.orphan_tickers:
        logger.warning(
            "Parquet 검증 orphan(기대에 없는데 적재됨) %d개: %s",
            len(report.orphan_tickers),
            ", ".join(report.orphan_tickers),
        )
    if not report.passed:
        _raise_verification_error(report)
    return report


def _diff_expected(
    expected: dict[str, TickerExpectation] | None,
    actual_counts: dict[str, int],
) -> tuple[tuple[str, ...], tuple[tuple[str, int, int], ...], tuple[str, ...]]:
    """expected(기대) vs actual(실제 ticker별 행수) 대조 → (missing, shortfall, orphan).

    - missing: 기대에 있는데 실제 0행(키 부재) — 조용한 소실(BLOCKING)
    - shortfall: 실제 행수 < 기대 행수 — 부분 소실(BLOCKING). (ticker, expected, actual)
    - orphan: 기대에 없는데 실제 존재 — 추가 데이터(경고만)
    expected=None 이면 대조 안 함(세 집합 모두 빈 tuple). actual 이 기대 이상이면 정상(재적재 등).
    """
    if expected is None:
        return (), (), ()
    missing: list[str] = []
    shortfall: list[tuple[str, int, int]] = []
    for ticker, exp in expected.items():
        actual = actual_counts.get(ticker, 0)
        if actual == 0:
            missing.append(ticker)
        elif actual < exp.row_count:
            shortfall.append((ticker, exp.row_count, actual))
    orphan = [t for t in actual_counts if t not in expected]
    return tuple(sorted(missing)), tuple(sorted(shortfall)), tuple(sorted(orphan))


def _raise_verification_error(report: VerificationReport) -> None:
    """게이트 실패를 어느 항목이 얼마나 위반했는지 명시해 raise(빈 통과·조용한 실패 금지)."""
    missing = ", ".join(report.missing_tickers) if report.missing_tickers else "없음"
    shortfall = (
        ", ".join(f"{t}(기대={e},실제={a})" for t, e, a in report.shortfall_tickers)
        if report.shortfall_tickers
        else "없음"
    )
    raise VerificationError(
        "Parquet 무결성 게이트 실패(금융 BLOCKING): "
        f"중복={report.duplicate_count}, adj_factor<=0={report.nonpositive_adj_factor_count}, "
        f"가격<=0={report.nonpositive_price_count}, OHLC위반={report.ohlc_violation_count}, "
        f"누락(소실)={missing}, 행수미달={shortfall}. "
        "기대 종목이 조용히 누락되면 생존편향 누수이므로 적재 데이터를 신뢰할 수 없습니다."
    )


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


def _ticker_row_counts(
    con: DuckDBPyConnection, sql: str, params: dict[str, object]
) -> dict[str, int]:
    """ticker별 실제 적재 행수 맵(expected 대조용). GROUP BY 결과를 {ticker: count} 로 환원."""
    counts: dict[str, int] = {}
    for row in con.execute(sql, params).fetchall():
        if row[0] is None:
            continue
        counts[str(row[0])] = int(row[1])
    return counts


def list_dataset_tickers(base_dir: Path) -> list[str]:
    """적재된 Parquet 트리의 DISTINCT ticker 정렬 리스트. 빈 트리면 빈 리스트.

    EDGAR 재무 적재(edgar.__main__)가 "가격이 있는 종목"만 companyfacts 를 받도록 — 전체
    ticker_cik(수만 건)이 아니라 이 교집합으로 SEC 호출을 최소화(rate limit·공정접근). 읽기 전용.
    """
    dataset_root = base_dir / _DATASET_NAME
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        logger.info("ticker 목록 스캔 대상 Parquet 없음 — 빈 리스트: dataset=%s", dataset_root)
        return []

    import duckdb

    glob = f"{dataset_root}/**/*.parquet"
    con = duckdb.connect(database=":memory:")
    try:
        rows = con.execute(_SQL_DISTINCT_TICKERS, {"glob": glob}).fetchall()
    finally:
        con.close()
    return [str(row[0]) for row in rows if row[0] is not None]
