"""파일럿(pilot.py) 모킹 단위 테스트 — 라이브 0(FakeSource 주입·tmp_path).

run_pilot 은 DataSource 를 주입받으므로 라이브 호출 없이 합성 소스로 오케스트레이션·분할 교차검증
로직을 검증한다. rate limit 전파, 분할 직전 거래일 adj_factor 추출 정확성에 집중.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from stockpick.data.pilot import PilotSymbol, _compute_split_check, run_pilot
from stockpick.data.storage import VerificationError
from stockpick.data.tiingo import TiingoRateLimitError
from stockpick.types import DailyBar, Exchange, Stock

if TYPE_CHECKING:
    from collections.abc import Sequence


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

    def iter_universe(self, *, include_delisted: bool = True) -> list[Stock]:
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


def test_run_pilot_detects_silent_loss_via_cumulative_expected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⭐ 회귀 봉인(라이브 파일럿 버그 재현): 어떤 종목 적재가 이전 종목을 조용히 소실시키면
    run_pilot 의 누적 expected 대조가 VerificationError 로 시끄럽게 실패한다.

    원래 버그: write 가 파티션 단위 purge 라 같은 NASDAQ·연도를 공유하는 이전 ticker 가 사라졌고
    게이트는 "현재 트리"만 봐 PASS 했다. 여기선 write_daily_bars 를 'purge 후 단일 ticker만 남김'
    으로 패치해 그 소실을 인위 재현 → 누적 expected 가 이제 누락을 잡는지 확인.
    """
    import stockpick.data.pilot as pilot_mod
    from stockpick.data import storage

    state: dict[str, str] = {}

    def _lossy_write(
        bars: Sequence[DailyBar],
        *,
        exchange: Exchange,
        base_dir: Path,
        source: str,
        ingested_at: datetime | None = None,
    ) -> Path:
        # 버그 재현: 매 적재마다 dataset 트리를 비우고 이번 ticker 만 남긴다(이전 ticker 소실).
        root = base_dir / "daily_bar"
        if root.exists():
            for p in root.rglob("*.parquet"):
                p.unlink()
        tickers = {b.ticker for b in bars}
        state["last"] = ", ".join(sorted(tickers))
        return storage.write_daily_bars(
            bars, exchange=exchange, base_dir=base_dir, source=source, ingested_at=ingested_at
        )

    monkeypatch.setattr(pilot_mod, "write_daily_bars", _lossy_write)

    # 같은 NASDAQ 에 두 ticker — 두 번째 적재가 첫 번째를 소실시킨다.
    source = _FakeSource(
        {
            "AAPL": [_bar("AAPL", date(2024, 6, 6), adj_factor="0.25")],
            "MSFT": [_bar("MSFT", date(2024, 6, 6))],
        }
    )
    # AAPL(누적 expected={AAPL}) 적재 후엔 PASS 하나, MSFT 적재가 AAPL 을 소실시키면
    # 누적 expected={AAPL,MSFT} 대비 AAPL 누락 → 게이트 FAIL.
    with pytest.raises(VerificationError, match="AAPL"):
        run_pilot(source=source, base_dir=tmp_path, delay_sec=0.0)
