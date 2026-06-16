"""파일럿(pilot.py) 모킹 단위 테스트 — 라이브 0(FakeSource 주입·tmp_path).

run_pilot 은 DataSource 를 주입받으므로 라이브 호출 없이 합성 소스로 오케스트레이션·분할 교차검증
로직을 검증한다. rate limit 전파, 분할 직전 거래일 adj_factor 추출 정확성에 집중.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from stockpick.data.pilot import PilotSymbol, _compute_split_check, run_pilot
from stockpick.data.tiingo import TiingoRateLimitError
from stockpick.types import DailyBar, Exchange


def _bar(ticker: str, d: date, adj_factor: str = "1") -> DailyBar:
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
    """DataSource 구조적 구현 — 주어진 ticker→bars 맵을 반환. iter_universe 는 미사용."""

    def __init__(self, data: dict[str, list[DailyBar]]) -> None:
        self._data = data

    @property
    def name(self) -> str:
        return "fake"

    def iter_universe(self, *, include_delisted: bool = True) -> list:  # type: ignore[type-arg]
        raise NotImplementedError

    def fetch_daily_bars(
        self, ticker: str, *, start: date | None = None, end: date | None = None
    ) -> list[DailyBar]:
        return self._data.get(ticker, [])


class _RateLimitSource(_FakeSource):
    def fetch_daily_bars(
        self, ticker: str, *, start: date | None = None, end: date | None = None
    ) -> list[DailyBar]:
        raise TiingoRateLimitError("rate limit")


def test_compute_split_check_picks_prev_trade_date() -> None:
    """분할 직전 거래일(split_date 미만 최댓값)의 adj_factor 를 정확히 추출."""
    symbol = PilotSymbol("AAPL", Exchange.NASDAQ, "4:1", date(2020, 8, 31), 4)
    bars = [
        _bar("AAPL", date(2020, 8, 27), adj_factor="0.249"),
        _bar("AAPL", date(2020, 8, 28), adj_factor="0.250"),  # 직전 거래일
        _bar("AAPL", date(2020, 8, 31), adj_factor="1.000"),  # 분할 당일(이후)
    ]
    sc = _compute_split_check(bars, symbol)
    assert sc is not None
    assert sc.prev_trade_date == date(2020, 8, 28)
    assert sc.prev_adj_factor == Decimal("0.250")
    assert sc.expected_factor == Decimal(1) / Decimal(4)


def test_compute_split_check_none_for_nonsplit() -> None:
    """분할 정의 없는 종목은 split_check=None."""
    symbol = PilotSymbol("MSFT", Exchange.NASDAQ, "무분할")
    assert _compute_split_check([_bar("MSFT", date(2020, 1, 2))], symbol) is None


def test_compute_split_check_insufficient_data() -> None:
    """분할 직전 거래일 데이터가 없으면 prev_* = None(데이터 부족 — 실패 아님)."""
    symbol = PilotSymbol("NVDA", Exchange.NASDAQ, "10:1", date(2024, 6, 7), 10)
    bars = [_bar("NVDA", date(2024, 6, 10))]  # 분할 이후만
    sc = _compute_split_check(bars, symbol)
    assert sc is not None
    assert sc.prev_adj_factor is None
    assert sc.expected_factor == Decimal(1) / Decimal(10)


def test_run_pilot_orchestrates_and_verifies(tmp_path: Path) -> None:
    """run_pilot: fetch→적재→검증→분할체크. 유니버스 종목 중 데이터 있는 것만 적재되고 PASS."""
    # _UNIVERSE 의 ticker 일부에만 데이터 공급 — 나머지는 빈 결과(no-op).
    source = _FakeSource(
        {
            "AAPL": [
                _bar("AAPL", date(2020, 8, 28), adj_factor="0.25"),
                _bar("AAPL", date(2020, 9, 1), adj_factor="1"),
            ],
            "MSFT": [_bar("MSFT", date(2019, 1, 2))],
        }
    )
    results = run_pilot(source=source, base_dir=tmp_path, delay_sec=0.0)
    by_ticker = {r.ticker: r for r in results}
    assert by_ticker["AAPL"].bar_count == 2
    assert by_ticker["AAPL"].report.passed
    # AAPL 분할 직전 거래일 adj_factor 추출 확인
    assert by_ticker["AAPL"].split_check is not None
    assert by_ticker["AAPL"].split_check.prev_adj_factor == Decimal("0.25")
    # 데이터 없는 종목은 0행
    assert by_ticker["JNJ"].bar_count == 0


def test_run_pilot_propagates_rate_limit(tmp_path: Path) -> None:
    """rate limit 발생 시 즉시 전파(조용히 중단·빈 결과 금지)."""
    source = _RateLimitSource({})
    with pytest.raises(TiingoRateLimitError):
        run_pilot(source=source, base_dir=tmp_path, delay_sec=0.0)
