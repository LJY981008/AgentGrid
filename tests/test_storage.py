"""저장층(storage.py) 모킹 단위 테스트 — 라이브 0(합성 DailyBar·tmp_path Parquet).

검증 항목(M1 §5 BLOCKING):
- Decimal 정밀 보존: 소수 4자리 가격·고정밀 adj_factor round-trip 후 손실 없음(float 캐스트 금지).
- Hive 파티션 경로: exchange={EX}/year={YYYY}/ 디렉토리 생성.
- 멱등(중복 방지): 같은 (ticker,trade_date) 재적재 시 행수 불변·중복 0.
- 검증 함수 게이트: 정상 PASS / adj_factor<=0·OHLC부정합·중복 → FAIL(VerificationError).
- 정밀도 초과: scale 한도 초과 Decimal → PrecisionError(조용한 반올림 금지).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from stockpick.data.storage import (
    PrecisionError,
    VerificationError,
    verify_parquet,
    write_daily_bars,
)
from stockpick.types import DailyBar, Exchange


def _bar(
    ticker: str,
    d: date,
    *,
    open_: str = "100.0000",
    high: str = "110.0000",
    low: str = "90.0000",
    close: str = "105.0000",
    volume: int = 1000,
    value: int | None = None,
    adj_factor: str = "1",
) -> DailyBar:
    return DailyBar(
        ticker=ticker,
        trade_date=d,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        value=value,
        adj_factor=Decimal(adj_factor),
    )


def _read_all(base_dir: Path) -> list[dict[str, object]]:
    """적재된 Parquet 트리를 pyarrow 로 직접 읽어 행 dict 리스트 반환(검증함수와 독립 경로)."""
    root = base_dir / "daily_bar"
    files = sorted(root.rglob("*.parquet"))
    rows: list[dict[str, object]] = []
    for f in files:
        # pyarrow.parquet.read_table 은 stub 미타이핑(untyped) — strict no-untyped-call 만 예외.
        rows.extend(pq.read_table(str(f)).to_pylist())  # type: ignore[no-untyped-call]
    return rows


def test_decimal_precision_preserved(tmp_path: Path) -> None:
    """가격·고정밀 adj_factor 가 round-trip 후 Decimal 로 손실 없이 보존(float 다운캐스트 금지)."""
    # adjClose/close 형태의 긴 소수 factor(분할 케이스 모사) — float 면 깨질 정밀도
    factor = Decimal("127.46") / Decimal("129.04")  # scale 28
    bar = _bar("AAPL", date(2020, 8, 28), close="129.0400", adj_factor=str(factor))
    write_daily_bars(
        [bar],
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="tiingo",
        ingested_at=datetime(2026, 6, 16, tzinfo=UTC),
    )
    rows = _read_all(tmp_path)
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row["close"], Decimal)
    assert row["close"] == Decimal("129.0400")
    assert isinstance(row["adj_factor"], Decimal)
    assert row["adj_factor"] == factor  # 정밀 보존(반올림·다운캐스트 없음)


def test_hive_partition_layout(tmp_path: Path) -> None:
    """exchange/year Hive 파티션 디렉토리가 정확히 생성된다(연도별 분리 포함)."""
    bars = [_bar("MSFT", date(2019, 3, 1)), _bar("MSFT", date(2020, 3, 2))]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")
    assert (tmp_path / "daily_bar" / "exchange=NASDAQ" / "year=2019").is_dir()
    assert (tmp_path / "daily_bar" / "exchange=NASDAQ" / "year=2020").is_dir()


def test_idempotent_reload_no_duplicates(tmp_path: Path) -> None:
    """같은 (ticker,trade_date) 배치를 두 번 적재해도 중복 누적 없음(멱등 덮어쓰기)."""
    bars = [_bar("JNJ", date(2021, 1, 4)), _bar("JNJ", date(2021, 1, 5))]
    write_daily_bars(bars, exchange=Exchange.NYSE, base_dir=tmp_path, source="tiingo")
    write_daily_bars(bars, exchange=Exchange.NYSE, base_dir=tmp_path, source="tiingo")
    rows = _read_all(tmp_path)
    assert len(rows) == 2  # 4 가 아니라 2 — 덮어쓰기
    report = verify_parquet(tmp_path)
    assert report.duplicate_count == 0
    assert report.passed


def test_same_partition_different_tickers_preserved(tmp_path: Path) -> None:
    """⭐ 회귀 봉인(라이브 파일럿 버그): 같은 (exchange, year) 파티션에 ticker 따로
    적재해도 서로 데이터 안 지워진다. (단일 파티션 파일이면 마지막 ticker 만 남아 소실됐음.)
    """
    write_daily_bars(
        [_bar("AAPL", date(2024, 6, 6))],
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="tiingo",
    )
    write_daily_bars(
        [_bar("NVDA", date(2024, 6, 6))],  # 같은 NASDAQ·2024 파티션, 다른 ticker
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="tiingo",
    )
    report = verify_parquet(tmp_path)
    assert report.ticker_count == 2  # 둘 다 보존(1 이 아님 — 소실 회귀 차단)
    assert report.row_count == 2
    assert report.passed


def test_verify_passes_clean_data(tmp_path: Path) -> None:
    """정상 데이터 검증 PASS + 리포트(행수·종목수·기간) 정확."""
    bars = [
        _bar("AAPL", date(2022, 6, 1)),
        _bar("AAPL", date(2022, 6, 2)),
        _bar("TSLA", date(2022, 6, 1)),
    ]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")
    report = verify_parquet(tmp_path)
    assert report.passed
    assert report.row_count == 3
    assert report.ticker_count == 2
    assert report.min_date == "2022-06-01"
    assert report.max_date == "2022-06-02"


def test_verify_fails_nonpositive_adj_factor(tmp_path: Path) -> None:
    """adj_factor<=0 행이 있으면 검증 게이트 실패(VerificationError)."""
    bars = [_bar("BAD", date(2022, 6, 1), adj_factor="0")]
    write_daily_bars(bars, exchange=Exchange.NYSE, base_dir=tmp_path, source="tiingo")
    with pytest.raises(VerificationError, match="adj_factor"):
        verify_parquet(tmp_path)


def test_verify_fails_ohlc_violation(tmp_path: Path) -> None:
    """high<low 등 OHLC 부정합 행이 있으면 검증 게이트 실패."""
    bars = [_bar("BAD", date(2022, 6, 1), high="90.0000", low="100.0000")]
    write_daily_bars(bars, exchange=Exchange.NYSE, base_dir=tmp_path, source="tiingo")
    with pytest.raises(VerificationError, match="OHLC"):
        verify_parquet(tmp_path)


def test_precision_error_on_scale_overflow(tmp_path: Path) -> None:
    """가격 scale(10) 초과 Decimal → PrecisionError(조용한 반올림 금지)."""
    # 소수 12자리 — _PRICE_SCALE=10 초과
    bar = _bar("AAPL", date(2022, 6, 1), close="105.123456789012")
    with pytest.raises(PrecisionError, match="close"):
        write_daily_bars([bar], exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")


def test_empty_input_is_noop(tmp_path: Path) -> None:
    """빈 입력은 파일 미생성(no-op), 검증은 0행 리포트(passed)."""
    write_daily_bars([], exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")
    report = verify_parquet(tmp_path)
    assert report.row_count == 0
    assert report.passed


def test_source_and_ingested_at_recorded(tmp_path: Path) -> None:
    """재현성 메타: 모든 행에 source·ingested_at 동반."""
    stamp = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
    bars = [_bar("AAPL", date(2022, 6, 1))]
    write_daily_bars(
        bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo", ingested_at=stamp
    )
    rows = _read_all(tmp_path)
    assert rows[0]["source"] == "tiingo"
    assert rows[0]["ingested_at"] == stamp


def test_value_nullable_roundtrip(tmp_path: Path) -> None:
    """value(거래대금) 미제공 None 이 round-trip 후에도 None 보존(추측 채움 금지)."""
    bars = [_bar("AAPL", date(2022, 6, 1), value=None)]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")
    rows = _read_all(tmp_path)
    assert rows[0]["value"] is None
