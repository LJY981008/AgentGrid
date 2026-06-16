"""가격 데이터 소스 어댑터 계약 — `DataSource` Protocol (ADR-002).

소스 교체 자유(Tiingo 파일럿 → Sharadar SEP 본격, M2)를 위해 가격 소스의 인터페이스를
`typing.Protocol` 로 추상화한다. 구체 HTTP·인증·rate-limit 구현은 B-pipeline 에서 각 어댑터가
담당하고, 이 모듈은 **계약만** 정의한다 — import 시 외부 의존성 0(stdlib만).

모듈 경계(python-conventions): `data` 는 `rules`/`backtest`/상위(api·webapp)를 import 하지
않는다. 도메인 계약(`..types`)만 의존한다.

생존편향 BLOCKING: `iter_universe` 는 **폐지 종목을 포함**해야 한다(현 상장만 반환 금지).
어댑터가 폐지 커버리지를 제공 못 하면 그 한계를 호출부에 명시적으로 드러내야 하며(빈 결과로
조용히 누락 금지), 무료 소스(Tiingo)의 폐지 미제공은 M1 게이트에서 정량 고지 대상이다.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..types import DailyBar, Stock


@runtime_checkable
class DataSource(Protocol):
    """가격 데이터 소스 어댑터 인터페이스.

    Tiingo·Sharadar 양쪽이 구현 가능하도록 추상적으로 정의. 식별자 모델은 ADR-002 를 따른다:
    종목 유니버스는 안정 식별자(CIK)를 가진 `Stock` 으로, 일봉은 가격 키(ticker)로 조회한다.
    `runtime_checkable` — 테스트에서 구현체의 구조적 적합성을 isinstance 로 스모크 가능
    (메서드 존재 여부만 검사하며 시그니처까지는 보지 않음에 유의).
    """

    @property
    def name(self) -> str:
        """소스 식별 라벨(예: "tiingo", "sharadar-sep"). 적재 행의 source 컬럼·로그·재현성용."""
        ...

    def iter_universe(self, *, include_delisted: bool = True) -> list[Stock]:
        """종목 유니버스를 반환. 기본은 폐지 종목 포함(생존편향 회피).

        include_delisted=True 가 기본 — 백테스트·랭킹은 폐지 종목을 반드시 포함해야 한다
        (현 상장만으로 과거 수익률 계산 금지). 소스가 폐지 커버리지를 제공하지 못하면 그 사실을
        호출부가 알 수 있어야 한다(조용한 누락 금지). 반환 `Stock` 은 안정 식별자 cik 를 채운다.
        """
        ...

    def fetch_daily_bars(
        self,
        ticker: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[DailyBar]:
        """단일 ticker 의 일봉(EOD)을 [start, end] 구간으로 조회(경계 포함, 시변 ticker 키).

        start/end=None 은 소스가 제공하는 전체 가용 구간을 의미한다. 반환 `DailyBar` 는 원주가
        (raw) + adj_factor 를 채우며(수정주가 원본 불변 BLOCKING), 룩어헤드 방지를 위해 호출부는
        시점 t 결정에 trade_date <= t 인 행만 사용해야 한다(이 계약은 구간 필터만 제공). 결측·
        거래정지 구간은 추측 채움 없이 누락 행으로 둔다.
        """
        ...
