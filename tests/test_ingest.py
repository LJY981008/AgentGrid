"""generic 적재기(ingest.py) 모킹 단위 테스트 — 라이브 0(FakeSource 주입·tmp_path).

ingest_tickers 는 DataSource 를 주입받으므로 라이브 호출 없이 합성 소스로 검증한다. 집중 항목:
- 정상 적재 + 누적 verify PASS, 집계(행수·종목수) 정확.
- 0행 종목(데이터 부족)을 조용한 누락 없이 명확히 집계(empty_tickers).
- 소실(같은 파티션의 이전 ticker 가 사라짐) → 누적 expected 대조가 VerificationError(시끄러운 실패).
- 공통 원인 에러(auth/ratelimit)는 즉시 전파, 종목별 응답 오류는 집계 후 진행(부분 실패 명시).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from stockpick.data.eodhd import EodhdAuthError, EodhdRateLimitError, EodhdResponseError
from stockpick.data.ingest import IngestSummary, ingest_tickers
from stockpick.data.storage import VerificationError
from stockpick.types import DailyBar, Exchange, Stock

if TYPE_CHECKING:
    from collections.abc import Sequence


def _bar(ticker: str, d: date, *, adj_factor: str = "1") -> DailyBar:
    return DailyBar(
        ticker=ticker,
        trade_date=d,
        open=Decimal("100.0000"),
        high=Decimal("110.0000"),
        low=Decimal("90.0000"),
        close=Decimal("105.0000"),
        volume=1000,
        value=None,
        adj_factor=Decimal(adj_factor),
    )


class _FakeSource:
    """DataSource 구조적 구현 — ticker→bars 맵 반환. 빈 결과 종목은 맵에서 빠짐(0행)."""

    def __init__(self, data: dict[str, list[DailyBar]]) -> None:
        self._data = data

    @property
    def name(self) -> str:
        return "fake"

    def iter_universe(self, *, include_delisted: bool = True) -> list[Stock]:
        raise NotImplementedError

    def fetch_daily_bars(
        self, ticker: str, *, start: date | None = None, end: date | None = None
    ) -> list[DailyBar]:
        return self._data.get(ticker, [])


class _AuthErrorSource(_FakeSource):
    def fetch_daily_bars(
        self, ticker: str, *, start: date | None = None, end: date | None = None
    ) -> list[DailyBar]:
        raise EodhdAuthError("auth")


class _RateLimitSource(_FakeSource):
    def fetch_daily_bars(
        self, ticker: str, *, start: date | None = None, end: date | None = None
    ) -> list[DailyBar]:
        raise EodhdRateLimitError("rate limit")


class _PerTickerErrorSource(_FakeSource):
    """특정 ticker 만 EodhdResponseError 를 던지는 소스(종목별 부분 실패 재현)."""

    def __init__(self, data: dict[str, list[DailyBar]], *, bad: str) -> None:
        super().__init__(data)
        self._bad = bad

    def fetch_daily_bars(
        self, ticker: str, *, start: date | None = None, end: date | None = None
    ) -> list[DailyBar]:
        if ticker == self._bad:
            raise EodhdResponseError("bad symbol", status_code=404)
        return self._data.get(ticker, [])


def test_ingest_normal_passes_and_aggregates(tmp_path: Path) -> None:
    """정상 적재: 누적 verify PASS, 행수·종목수 집계 정확, 게이트 PASS."""
    source = _FakeSource(
        {
            "AAPL": [_bar("AAPL", date(2024, 1, 2)), _bar("AAPL", date(2024, 1, 3))],
            "JPM": [_bar("JPM", date(2024, 1, 2))],
        }
    )
    summary = ingest_tickers(
        source,
        [("AAPL", Exchange.NASDAQ), ("JPM", Exchange.NYSE)],
        base_dir=tmp_path,
    )
    assert isinstance(summary, IngestSummary)
    assert summary.passed
    assert summary.total_rows == 3
    assert summary.ingested_ticker_count == 2
    assert summary.empty_tickers == ()
    assert summary.failed_tickers == ()
    assert summary.report is not None
    assert summary.report.passed
    assert summary.report.row_count == 3
    assert summary.report.ticker_count == 2


def test_ingest_empty_ticker_aggregated_not_silent(tmp_path: Path) -> None:
    """0행 종목(데이터 부족)은 조용히 누락 않고 empty_tickers 로 명확 집계 — 소실 아님이라 PASS."""
    source = _FakeSource({"AAPL": [_bar("AAPL", date(2024, 1, 2))]})  # JPM 데이터 없음(0행)
    summary = ingest_tickers(
        source,
        [("AAPL", Exchange.NASDAQ), ("JPM", Exchange.NYSE)],
        base_dir=tmp_path,
    )
    assert summary.empty_tickers == ("JPM",)
    assert summary.ingested_ticker_count == 1
    assert summary.total_rows == 1
    # 0행은 데이터 부족이지 소실이 아니므로 게이트는 통과(actual 0 과 expected 정합).
    assert summary.passed


def test_ingest_no_data_at_all_reports_none(tmp_path: Path) -> None:
    """전 종목 0행이면 적재 트리 없음 → report=None, passed=False(데이터셋 생성 실패 명시)."""
    source = _FakeSource({})  # 어떤 ticker 도 데이터 없음
    summary = ingest_tickers(
        source,
        [("AAPL", Exchange.NASDAQ), ("JPM", Exchange.NYSE)],
        base_dir=tmp_path,
    )
    assert summary.report is None
    assert summary.total_rows == 0
    assert summary.empty_tickers == ("AAPL", "JPM")
    assert not summary.passed


def test_ingest_auth_error_propagates(tmp_path: Path) -> None:
    """인증 실패(전 종목 공통 원인)는 즉시 전파(조용히 빈 결과로 둔갑 금지)."""
    source = _AuthErrorSource({})
    with pytest.raises(EodhdAuthError):
        ingest_tickers(source, [("AAPL", Exchange.NASDAQ)], base_dir=tmp_path)


def test_ingest_rate_limit_propagates(tmp_path: Path) -> None:
    """rate limit(전 종목 공통 원인)은 즉시 전파."""
    source = _RateLimitSource({})
    with pytest.raises(EodhdRateLimitError):
        ingest_tickers(source, [("AAPL", Exchange.NASDAQ)], base_dir=tmp_path)


def test_ingest_per_ticker_error_aggregated_continues(tmp_path: Path) -> None:
    """종목별 응답 오류는 그 종목만 실패 집계하고 진행 — 정상 종목은 적재되되 전체 게이트는 FAIL."""
    source = _PerTickerErrorSource(
        {"AAPL": [_bar("AAPL", date(2024, 1, 2))]},
        bad="BADX",
    )
    summary = ingest_tickers(
        source,
        [("BADX", Exchange.NASDAQ), ("AAPL", Exchange.NASDAQ)],
        base_dir=tmp_path,
    )
    # 정상 종목 AAPL 은 적재됨
    assert summary.ingested_ticker_count == 1
    assert summary.total_rows == 1
    # 실패 종목은 명확 집계
    assert summary.failed_tickers == ("BADX",)
    # 부분 실패가 있으면 전체 게이트 FAIL(조용한 부분 누락 금지) — verify 자체는 AAPL 만 봐 PASS여도
    assert summary.report is not None
    assert summary.report.passed
    assert not summary.passed


def test_ingest_detects_silent_loss_via_cumulative_expected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⭐ 소실 탐지: 어떤 종목 적재가 이전 종목을 조용히 소실시키면 누적 expected 대조가
    VerificationError 로 시끄럽게 실패한다(TASK-B 가드가 generic 적재기에서도 작동).

    pilot 테스트와 동형: write_daily_bars 를 'purge 후 이번 ticker 만 남김'으로 패치해 같은
    파티션의 이전 ticker 소실을 인위 재현.
    """
    import stockpick.data.ingest as ingest_mod
    from stockpick.data import storage

    def _lossy_write(
        bars: Sequence[DailyBar],
        *,
        exchange: Exchange,
        base_dir: Path,
        source: str,
        ingested_at: datetime | None = None,
    ) -> Path:
        root = base_dir / "daily_bar"
        if root.exists():
            for p in root.rglob("*.parquet"):
                p.unlink()
        return storage.write_daily_bars(
            bars, exchange=exchange, base_dir=base_dir, source=source, ingested_at=ingested_at
        )

    monkeypatch.setattr(ingest_mod, "write_daily_bars", _lossy_write)

    # 같은 NASDAQ 두 ticker — 두 번째(MSFT) 적재가 첫 번째(AAPL)를 소실시킨다.
    source = _FakeSource(
        {
            "AAPL": [_bar("AAPL", date(2024, 6, 6))],
            "MSFT": [_bar("MSFT", date(2024, 6, 6))],
        }
    )
    with pytest.raises(VerificationError, match="AAPL"):
        ingest_tickers(
            source,
            [("AAPL", Exchange.NASDAQ), ("MSFT", Exchange.NASDAQ)],
            base_dir=tmp_path,
        )
