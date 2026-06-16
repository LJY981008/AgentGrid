"""도메인 계약 타입 원본 — stock-1st_plan §6 데이터 요구사항의 코드화.

변경 시 기획 문서와 동기 유지. 순수 도메인은 dataclass, 외부 입력(API 응답·CSV) 검증은
경계에서 별도(pydantic 등, M1 도입). 누락 필드는 추측값 금지 — 명시적 None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class Market(str, Enum):
    """시장 구분."""

    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"


@dataclass(frozen=True, slots=True)
class Stock:
    """종목 마스터. 폐지 종목 포함(생존편향 회피 — delisted_at 보존)."""

    code: str  # 6자리 종목코드
    name: str
    market: Market
    listed_at: date | None
    delisted_at: date | None  # None = 현재 상장 중


@dataclass(frozen=True, slots=True)
class DailyBar:
    """일봉(EOD) OHLCV — 원주가(raw, 미수정) 저장.

    수정주가는 adjusted = raw * adj_factor 로 재계산(원본 불변). 수정 기준은 단일 소스
    (FDR adjusted)로 통일하고 액면분할 표본으로 교차검증(M1). 가격은 Decimal — float 금지
    (정밀도 BLOCKING, 부동소수 오차로 수익률 왜곡 방지). 누락 필드는 추측 금지 — 명시적 None.
    """

    code: str
    trade_date: date
    open: Decimal  # 원주가(미수정)
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    value: int | None  # 거래대금(원), 미제공 시 None
    adj_factor: Decimal = Decimal("1")  # 누적조정계수, adjusted = raw*adj_factor (무수정=1)


@dataclass(frozen=True, slots=True)
class TopEntry:
    """Top20/Top5 랭킹 엔트리. score = 정량 룰 산출 점수, rank = 1-based 순위."""

    code: str
    market: Market
    rank: int
    score: float
    # 룰 버전(보정 이력 추적) + 산출 근거(팩터별 기여) — 재현성·투명성
    rule_version: str
    factors: dict[str, float]
