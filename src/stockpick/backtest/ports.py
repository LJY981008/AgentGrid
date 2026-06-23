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
    from ..rules.factors import MomentumScore
    from ..types import Exchange


def momentum_window_days(lookback_days: int, skip_recent_days: int) -> int:
    """momentum lookback+skip 거래일을 덮는 load 윈도우 캘린더일 = (lookback+skip)*2+30.

    거래일≈캘린더×5/7 → ×2 면 lookback+skip 거래일 확실 포함·+30 여유. **단일 출처**:
    engine._window_start(메모리 경로 load_range 하한)와 DuckDBPriceSeriesPort.momentum_scores
    (SQL 윈도우)가 동일 윈도우를 쓰도록 강제한다 — 둘이 어긋나면 windowed momentum bit-identical
    이 깨진다(BLOCKING·ADR-007). 상장 초기·sparse 종목은 가용 전부로 graceful 축소(양쪽 동일).
    """
    return (lookback_days + skip_recent_days) * 2 + 30


@runtime_checkable
class PriceSeriesPort(Protocol):
    def load(self, *, as_of: date) -> dict[str, list[PricePoint]]:
        """ticker별 수정주가 시계열(trade_date <= as_of). 룩어헤드 1차 가드."""
        ...

    def full_series(self) -> dict[str, list[PricePoint]]:
        """전구간 시계열(수익 실현용). ⚠️ 대용량 OOM — 엔진은 `load_range`(종목×구간) 사용.
        full_series 는 소규모 폴백·테스트용."""
        ...

    def load_range(
        self, *, tickers: set[str], start: date, end: date
    ) -> dict[str, list[PricePoint]]:
        """종목집합 × [start, end] 구간 수정주가(메모리 절감 — full_series 전체 대신). 랭킹 윈도우로
        쓸 때 `end=as_of` 면 trade_date<=as_of(룩어헤드 상한 유지). 빈 tickers→{}."""
        ...

    def tickers_with_data(self, *, tickers: set[str], start: date, end: date) -> set[str]:
        """tickers 중 [start, end] 구간에 봉이 1개 이상 있는 종목 집합(멤버십만·가격 미로드).

        `load_range(tickers, start, end)` 의 **키 집합과 동치**(동일 WHERE — 봉≥1)이되 PricePoint
        를 물질화하지 않는다(SQL `DISTINCT ticker`). 벤치 등 멤버십만 필요한 곳의 OOM/속도 최적화.
        빈 tickers→빈 집합."""
        ...

    def trading_days(self) -> list[date]:
        """데이터에 존재하는 정렬된 거래일 합집합(calendar 입력)."""
        ...

    def ticker_exchanges(self) -> dict[str, Exchange]:
        """ticker → Exchange(랭킹 그룹핑·TopEntry.exchange 채움). 가격 저장소 파티션 키에서 도출."""
        ...


@runtime_checkable
class MomentumScorePort(Protocol):
    """momentum 점수를 저장소에서 직접 산출(SQL 부분 푸시다운·ADR-007). 옵트인 — PriceSeriesPort
    와 별개 Protocol 이라 Fake/Parquet 은 미구현(엔진이 isinstance 로 분기해 메모리 경로 폴백).

    DuckDBPriceSeriesPort 만 구현한다(`momentum_endpoints`+`momentum_from_endpoints`로 끝점 2점만
    스캔·1억행 풀로드 회피). 결과는 `momentum_universe(load_range(tradable, _window_start(t), t))`
    (메모리 경로)와 **bit-identical**(windowed wn 기준·룩어헤드 trade_date<=as_of).
    """

    def momentum_scores(
        self,
        *,
        tickers: set[str],
        as_of: date,
        lookback_days: int,
        skip_recent_days: int,
    ) -> dict[str, MomentumScore]:
        """tickers × as_of momentum 점수. 산출불가(2점미만)도 None 점수로 포함(momentum_universe
        와 동일)·윈도우 봉 0 종목만 제외(load_range 봉 0 제외와 동일·스테일 배제). 빈 tickers→{}.
        윈도우 = momentum_window_days(lookback,skip)(engine._window_start 와 동일 출처)."""
        ...


@runtime_checkable
class UniversePort(Protocol):
    def constituents(self, *, as_of: date) -> set[str]:
        """as_of 시점 거래가능 ticker 집합(listed<=as_of and (boundary None or as_of<boundary)).

        ⚠️ boundary = **첫 거래불가일**(마지막 실거래일+1). MasterUniverse 는 스냅샷
        delisted_at(=마지막 실거래일 추정)을 +1day 변환해 이 규약에 주입한다(어댑터 책임).
        """
        ...

    def delisting_event(self, ticker: str) -> date | None:
        """ticker boundary(첫 거래불가일·없으면 None).

        엔진 `_price_before(boundary)` = 마지막 실봉 가격으로 청산.
        """
        ...

    def ticker_count(self) -> int:
        """유니버스 전체 멤버십 종목 수(시점 무관·demo top_n·리포트용·엔진 미사용)."""
        ...


@runtime_checkable
class IdentityResolver(Protocol):
    def cik_for(self, ticker: str, *, on: date) -> str:
        """시점 on 에서 ticker 의 cik(안정 식별자). 미해소면 빈 문자열(caveat 대상)."""
        ...
