"""백테스트 데모 smoke — 합성 Parquet 픽스처(라이브 0). end-to-end 골격 동작 확인."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from stockpick.backtest.demo import run_demo
from stockpick.data.storage import write_daily_bars
from stockpick.types import DailyBar, Exchange

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bars(ticker: str, days: list[date], base: int, step: int) -> list[DailyBar]:
    out: list[DailyBar] = []
    for i, d in enumerate(days):
        price = Decimal(base + step * i)
        out.append(
            DailyBar(
                ticker=ticker,
                trade_date=d,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1000,
                value=None,
                adj_factor=Decimal("1"),
            )
        )
    return out


def test_run_demo_empty_dir_guides(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = run_demo(tmp_path)
    assert rc == 0
    assert "수집 데이터 없음" in capsys.readouterr().out


def test_run_demo_with_synthetic_parquet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    days = _weekdays(date(2024, 1, 1), 200)
    ingested = datetime(2026, 6, 17, tzinfo=UTC)
    bars = _bars("AAA", days, 100, 1) + _bars("BBB", days, 100, 0)  # AAA 상승, BBB 평탄
    write_daily_bars(
        bars, exchange=Exchange.NASDAQ, base_dir=tmp_path, source="test", ingested_at=ingested
    )
    rc = run_demo(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "백테스트 골격 결과" in out
    assert "검증 전" in out  # 미검증 경고 노출
    assert "EQUAL_WEIGHT_UNIVERSE" in out  # 벤치 비교 출력
