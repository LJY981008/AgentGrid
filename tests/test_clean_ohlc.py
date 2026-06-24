"""A-1 정제 migration 테스트 — 더티 Parquet 생성→clean_parquet_ohlc→verify PASS."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from stockpick.data.clean_ohlc import clean_parquet_ohlc
from stockpick.data.storage import VerificationError, verify_parquet, write_daily_bars
from stockpick.types import DailyBar, Exchange


def _bar(ticker: str, d: date, *, o: str, h: str, low: str, c: str) -> DailyBar:
    return DailyBar(
        ticker=ticker,
        trade_date=d,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=100,
        value=None,
        adj_factor=Decimal("1"),
    )


def test_clean_parquet_ohlc_makes_verify_pass(tmp_path: Path) -> None:
    base = tmp_path / "parquet"
    base.mkdir()
    bars = [
        _bar("AAA", date(2024, 1, 2), o="10", h="12", low="9", c="11"),  # 정상(불변)
        _bar("AAA", date(2024, 1, 3), o="0", h="0", low="0", c="0"),  # 0봉 → drop(이슈①)
        _bar("AAA", date(2024, 1, 4), o="1353", h="1319", low="1319", c="1319"),  # carry-forward
        _bar("AAA", date(2024, 1, 5), o="630", h="633", low="630", c="635"),  # close>high
    ]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=base, source="t")

    # 정제 전: verify FAIL(VerificationError — 0봉 nonpositive + OHLC 위반)
    with pytest.raises(VerificationError):
        verify_parquet(base)

    report = clean_parquet_ohlc(base)
    assert report.files_targeted == 1
    assert report.files_rewritten == 1
    assert report.rows_dropped == 1  # 0봉 1개
    assert report.rows_clamped == 2  # carry-forward + close>high

    # 정제 후: verify PASS·0봉 1개 drop → 3행
    rep = verify_parquet(base)
    assert rep.passed
    assert rep.row_count == 3
    assert rep.nonpositive_price_count == 0
    assert rep.ohlc_violation_count == 0


def test_clean_targets_nonpositive_low_without_ordering_violation(tmp_path: Path) -> None:
    # CRITICAL 회귀(리뷰): low<=0·close>0·ordering OK 봉은 ordering 술어로 안 잡힘 → 셀렉터가
    # verify nonpositive(low<=0)와 동형이어야 영향 파일 선택됨. 구 셀렉터(close<=0만)면 FAIL 잔존.
    base = tmp_path / "parquet"
    base.mkdir()
    write_daily_bars(
        [
            _bar("AAA", date(2024, 1, 2), o="10", h="12", low="9", c="11"),  # 정상
            _bar("AAA", date(2024, 1, 3), o="10", h="12", low="0", c="11"),  # low<=0·ordering OK
        ],
        exchange=Exchange.NASDAQ,
        base_dir=base,
        source="t",
    )
    with pytest.raises(VerificationError):  # low=0 → nonpositive FAIL
        verify_parquet(base)
    report = clean_parquet_ohlc(base)
    assert report.files_targeted == 1  # 셀렉터가 low<=0 파일 선택
    assert report.rows_clamped == 1  # low<=0 봉 보정(drop 아님·close>0)
    rep = verify_parquet(base)
    assert rep.passed
    assert rep.row_count == 2  # drop 없음


def test_clean_parquet_ohlc_idempotent_on_clean_tree(tmp_path: Path) -> None:
    # 정상 트리는 정제 대상 0(멱등·결함 없으면 no-op).
    base = tmp_path / "parquet"
    base.mkdir()
    write_daily_bars(
        [_bar("BBB", date(2024, 1, 2), o="10", h="12", low="9", c="11")],
        exchange=Exchange.NYSE,
        base_dir=base,
        source="t",
    )
    report = clean_parquet_ohlc(base)
    assert report.files_targeted == 0
    assert verify_parquet(base).passed
