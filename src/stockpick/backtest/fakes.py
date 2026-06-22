"""테스트·데모용 합성 포트. 핵심 = FakeUniversePort 의 합성 폐지 주입(생존편향 가드 발동 증명).

무료 데이터엔 실제 폐지가 0건이라 가드가 한 번도 발동 안 됨 = 죽은 가드. 합성 폐지로 청산
경로·생존편향 sensitivity 를 TDD 로 봉인한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..types import Exchange

if TYPE_CHECKING:
    from datetime import date

    from ..rules._scan import PricePoint


class FakePriceSeriesPort:
    def __init__(
        self,
        series: dict[str, list[PricePoint]],
        exchanges: dict[str, Exchange] | None = None,
    ) -> None:
        self._series = series
        self._exchanges = exchanges or {}

    def load(self, *, as_of: date) -> dict[str, list[PricePoint]]:
        return {t: [p for p in pts if p.trade_date <= as_of] for t, pts in self._series.items()}

    def full_series(self) -> dict[str, list[PricePoint]]:
        return self._series

    def load_range(
        self, *, tickers: set[str], start: date, end: date
    ) -> dict[str, list[PricePoint]]:
        # _scan.load_range_series 동치 — tickers∩·[start,end] 슬라이스·빈 window ticker 제외.
        out: dict[str, list[PricePoint]] = {}
        for t, pts in self._series.items():
            if t not in tickers:
                continue
            window = [p for p in pts if start <= p.trade_date <= end]
            if window:
                out[t] = window
        return out

    def trading_days(self) -> list[date]:
        return sorted({p.trade_date for pts in self._series.values() for p in pts})

    def ticker_exchanges(self) -> dict[str, Exchange]:
        # 미지정 ticker 는 NASDAQ 기본(테스트 단순화 — 실전은 adapters 가 파티션 키에서 도출)
        return {t: self._exchanges.get(t, Exchange.NASDAQ) for t in self._series}


class FakeUniversePort:
    def __init__(self, listed: dict[str, date], delisted: dict[str, date | None]) -> None:
        self._listed = listed
        self._delisted = delisted

    def constituents(self, *, as_of: date) -> set[str]:
        out: set[str] = set()
        for ticker, listed_at in self._listed.items():
            delisted_at = self._delisted.get(ticker)
            if listed_at <= as_of and (delisted_at is None or as_of < delisted_at):
                out.add(ticker)
        return out

    def delisting_event(self, ticker: str) -> date | None:
        return self._delisted.get(ticker)

    def ticker_count(self) -> int:
        return len(self._listed)


class StubIdentityResolver:
    """골격용 — 주입된 ticker→cik 맵. 미해소면 빈 문자열(caveat). 실전=ticker_history(후속)."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = mapping

    def cik_for(self, ticker: str, *, on: date) -> str:  # noqa: ARG002 (on=시변, 골격은 무시)
        return self._mapping.get(ticker, "")
