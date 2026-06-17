"""백테스트 데이터 읽기 포트(Protocol·DI). backtest 는 라이브 API 가 아니라 저장소를 읽는다.

룩어헤드 BLOCKING: PriceSeriesPort.load(as_of) 는 랭킹용(<=as_of 만). full_series() 는 수익
실현용 전구간(엔진이 [t+1,t'] 만 잘라 씀). UniversePort.constituents(as_of) 는 가격파일 존재가
아니라 listed/delisted 기준 — survivorship 정답.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    from ..rules._scan import PricePoint
    from ..types import Exchange


@runtime_checkable
class PriceSeriesPort(Protocol):
    def load(self, *, as_of: date) -> dict[str, list[PricePoint]]:
        """ticker별 수정주가 시계열(trade_date <= as_of). 룩어헤드 1차 가드."""
        ...

    def full_series(self) -> dict[str, list[PricePoint]]:
        """전구간 시계열(수익 실현용 — 엔진이 진입일~청산일 구간만 슬라이스)."""
        ...

    def trading_days(self) -> list[date]:
        """데이터에 존재하는 정렬된 거래일 합집합(calendar 입력)."""
        ...

    def ticker_exchanges(self) -> dict[str, Exchange]:
        """ticker → Exchange(랭킹 그룹핑·TopEntry.exchange 채움). 가격 저장소 파티션 키에서 도출."""
        ...


@runtime_checkable
class UniversePort(Protocol):
    def constituents(self, *, as_of: date) -> set[str]:
        """as_of 시점 거래가능 ticker 집합(listed<=as_of and (delisted None or as_of<delisted))."""
        ...

    def delisting_event(self, ticker: str) -> date | None:
        """ticker 폐지일(없으면 None). 엔진이 보유구간 내 폐지 청산 판정에 사용."""
        ...


@runtime_checkable
class IdentityResolver(Protocol):
    def cik_for(self, ticker: str, *, on: date) -> str:
        """시점 on 에서 ticker 의 cik(안정 식별자). 미해소면 빈 문자열(caveat 대상)."""
        ...
