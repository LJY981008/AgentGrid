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
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from stockpick.data.storage import (
    PrecisionError,
    VerificationError,
    build_expected,
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
    """가격·adj_factor 가 round-trip 후 Decimal 로 손실 없이 보존(float 다운캐스트 금지).

    TASK-C: adj_factor 는 어댑터 공유 헬퍼가 소수 12자리로 quantize 한 값이 저장층에 들어온다
    (저장 컬럼 scale=12 와 정합). 따라서 분할 케이스 factor 도 12자리 quantize 값으로 모사한다.
    """
    # adjClose/close 형태 분할 factor 를 헬퍼와 동일하게 12자리 quantize(저장 컬럼 scale=12)
    factor = (Decimal("127.46") / Decimal("129.04")).quantize(
        Decimal("1E-12"), rounding=ROUND_HALF_EVEN
    )
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


def test_precision_error_on_adj_factor_scale_overflow(tmp_path: Path) -> None:
    """adj_factor scale(12) 초과 Decimal → PrecisionError(TASK-C: 어댑터 quantize 미적용 값 거부).

    어댑터 공유 헬퍼는 12자리로 quantize 하므로 정상 경로에선 발생 안 함. 이 테스트는 13자리 이상
    꼬리가 저장층까지 새어 들어오면(헬퍼 우회) 조용히 반올림 않고 명시적으로 실패함을 고정한다.
    """
    bar = _bar("AAPL", date(2022, 6, 1), adj_factor="0.1234567890123")  # 13자리 — scale 12 초과
    with pytest.raises(PrecisionError, match="adj_factor"):
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


# --- expected(기대) vs actual(실제) 대조 — 조용한 소실 탐지(생존편향 BLOCKING) ---


def test_verify_detects_silently_missing_ticker(tmp_path: Path) -> None:
    """⭐ 핵심 회귀(옛 버그가 PASS 했던 시나리오): expected={A,B,C} 인데 Parquet 에 A,B 만 있으면
    (C 가 조용히 소실) 게이트가 **반드시 FAIL** 하고 누락 ticker(C)를 보고한다.

    이전 게이트는 "현재 트리"(A,B)만 보고 dup/adj/OHLC 가 깨끗하니 PASS 했다 — 그래서 같은
    파티션의 이전 ticker 소실을 못 잡았다. expected 대조로 이제 잡는다.
    """
    # A, B, C 를 기대값으로 포착 — 그러나 C 는 적재하지 않는다(소실 시뮬레이션).
    all_bars = [
        _bar("A", date(2024, 6, 6)),
        _bar("B", date(2024, 6, 6)),
        _bar("C", date(2024, 6, 6)),
    ]
    expected = build_expected(all_bars)
    # A, B 만 실제 적재(C 소실)
    write_daily_bars(all_bars[:2], exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")

    with pytest.raises(VerificationError, match="C") as exc:
        verify_parquet(tmp_path, expected=expected)
    assert "누락" in str(exc.value)


def test_verify_passes_when_all_expected_present(tmp_path: Path) -> None:
    """expected 전부 존재 + 행수 일치 시 PASS, expected_checked=True."""
    bars = [
        _bar("A", date(2024, 6, 5)),
        _bar("A", date(2024, 6, 6)),
        _bar("B", date(2024, 6, 6)),
    ]
    expected = build_expected(bars)
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")
    report = verify_parquet(tmp_path, expected=expected)
    assert report.passed
    assert report.expected_checked
    assert report.missing_tickers == ()
    assert report.shortfall_tickers == ()


def test_verify_fails_on_row_count_shortfall(tmp_path: Path) -> None:
    """기대 행수보다 실제 행수가 적으면(부분 소실) FAIL + (ticker,expected,actual) 보고."""
    expected_bars = [
        _bar("A", date(2024, 6, 5)),
        _bar("A", date(2024, 6, 6)),  # A 는 2행 기대
    ]
    expected = build_expected(expected_bars)
    # 실제로는 A 1행만 적재(1행 소실)
    write_daily_bars(
        expected_bars[:1], exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo"
    )
    with pytest.raises(VerificationError, match="행수미달") as exc:
        verify_parquet(tmp_path, expected=expected)
    assert "A" in str(exc.value)
    assert "기대=2" in str(exc.value)


def test_verify_warns_orphan_but_passes(tmp_path: Path) -> None:
    """orphan(기대에 없는데 적재됨)은 경고만 — PASS(추가 데이터는 정합 위반 아님)."""
    bars = [_bar("A", date(2024, 6, 6)), _bar("ORPHAN", date(2024, 6, 6))]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")
    # 기대엔 A 만 — ORPHAN 은 기대 밖
    expected = build_expected([_bar("A", date(2024, 6, 6))])
    report = verify_parquet(tmp_path, expected=expected)
    assert report.passed  # orphan 은 fail 아님
    assert report.orphan_tickers == ("ORPHAN",)
    assert report.missing_tickers == ()


def test_verify_empty_tree_with_expected_fails_all_missing(tmp_path: Path) -> None:
    """빈 트리인데 expected 가 있으면 전량 소실(전부 missing) → FAIL(가장 위험한 케이스)."""
    expected = build_expected([_bar("A", date(2024, 6, 6)), _bar("B", date(2024, 6, 6))])
    # 아무것도 적재하지 않음
    with pytest.raises(VerificationError, match="누락") as exc:
        verify_parquet(tmp_path, expected=expected)
    assert "A" in str(exc.value)
    assert "B" in str(exc.value)


def test_verify_no_expected_skips_diff(tmp_path: Path) -> None:
    """expected 미전달이면 대조 건너뜀(expected_checked=False) — 기존 호출부 호환."""
    bars = [_bar("A", date(2024, 6, 6))]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="tiingo")
    report = verify_parquet(tmp_path)  # expected 없음
    assert report.passed
    assert report.expected_checked is False
    assert report.missing_tickers == ()


def test_build_expected_counts_rows_per_ticker() -> None:
    """build_expected: ticker별 행수 정확 집계(빈 입력은 빈 맵)."""
    assert build_expected([]) == {}
    exp = build_expected(
        [_bar("A", date(2024, 6, 5)), _bar("A", date(2024, 6, 6)), _bar("B", date(2024, 6, 6))]
    )
    assert exp["A"].row_count == 2
    assert exp["B"].row_count == 1
