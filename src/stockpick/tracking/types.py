"""추적 도메인 계약 타입 — 라운드·거래·현금흐름·분할 이벤트(스펙 §3~§4).

규약(기존 `stockpick.types` 관례): frozen slots dataclass·돈/수량=Decimal(float 금지·정밀도
BLOCKING)·시점=date·누락=명시 None. surrogate id 는 DB 생성이라 `id: int | None`(미영속=None).

⚠️ 측정 BLOCKING(스펙 §3.1): 수량·평단 보정은 **SPLIT 이벤트만** 사용 — `DailyBar.adj_factor`
는 분할+배당 혼합(total-return 계수)이라 여기 오용하면 배당락마다 유령 수량이 생긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime  # noqa: TC003 — 런타임 필드 타입
from decimal import Decimal
from enum import StrEnum


class TradeSide(StrEnum):
    """체결 방향 — DB CHECK('BUY','SELL') 와 동일 값."""

    BUY = "BUY"
    SELL = "SELL"


class RoundStatus(StrEnum):
    """라운드 상태 — open(활성·전역 1개)·closed(회고+성과 동결·불변)."""

    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Trade:
    """체결 1건(append-only). 정정은 soft-void(voided_at·void_reason 쌍) — 물리 수정/삭제 금지.

    stock_id(FK)=안정 식별(티커 재사용 대비), ticker=입력 당시 사실 보존(감사). price 는 raw
    체결가(사실) — 분할 반영은 원장 재생(ledger)이 SPLIT 이벤트로 수행.
    """

    id: int | None
    round_id: int
    stock_id: int
    ticker: str
    side: TradeSide
    quantity: Decimal  # >0 (방향은 side)
    price: Decimal  # >0 raw 체결 단가(USD)
    fee: Decimal  # >=0 수수료(USD)
    executed_on: date
    note: str | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CashFlow:
    """외부 자본 유출입(signed·≠0) — 입금 +, 출금 −. TWR 분모 보정(F_d)의 유일 원천(C-2).

    BUY/SELL 은 내부 이체(현금↔주식)라 여기 기록하지 않는다. soft-void 규약은 Trade 와 동일.
    """

    id: int | None
    round_id: int
    amount: Decimal
    flowed_on: date
    note: str | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SplitEvent:
    """분할 이벤트(corporate_action·kind='split'). ratio = 신주/구주(2-for-1 → 2, 1:10 역분할
    → 0.1). effective_on 장 시작 효력(일중 순서 규약 1번 — ledger 참조)."""

    ticker: str
    effective_on: date
    ratio: Decimal  # >0
    source: str
    ingested_at: datetime


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    """라운드 생성 시점 Top20 랭킹 1행(동결·JSONB 직렬화 대상).

    anchor_close = 앵커일(anchor_as_of) raw 종가 동결 — 모델 계열(②③)의 진입가 재현성
    (사후 재로드 시 vintage 모호성 제거·스펙 §3.4). 부재(가격 결측)면 None(그 종목 측정불가).
    """

    cik: str
    ticker: str
    exchange: str
    rank: int
    score: float
    factors: dict[str, float]
    anchor_close: Decimal | None


@dataclass(frozen=True, slots=True)
class CarryInPosition:
    """라운드 open 시점 이월 포지션 스냅샷(시스템 파생·리포팅 동결물).

    원장(전역 재생)이 유일 진실 — 이 스냅샷은 표시·감사용(closed 라운드 불변으로 재생과 일치가
    불변식). anchor_close = open 시점 직전 유효 종가(계열 ① 라운드 앵커)."""

    ticker: str
    quantity: Decimal
    anchor_close: Decimal | None


@dataclass(frozen=True, slots=True)
class RoundRetrospective:
    """구조화 회고(close 시 필수·스펙 §2) — outcome 아닌 process 채점을 유도하는 3필드."""

    judgment_good: str  # 잘한 판단(근거 포함)
    judgment_bad: str  # 잘못한 판단(근거 포함)
    rule_change: str  # 다음 라운드 규칙 변경(없으면 "없음" 명시)


@dataclass(frozen=True, slots=True)
class PortfolioRound:
    """월 라운드 컨테이너 — Top20 스냅샷(동결)+토의메모+Top5+회고+성과 동결.

    validated·rule_signature·g7_summary = 생성 시점 랭킹의 정직성 맥락 동결(미래에 룰이
    검증돼도 과거 라운드 라벨 불변). performance_snapshot 은 close 시 1회 동결(JSONB·불투명)
    — GET performance 는 항상 재생 기반이고 동결값과 괴리 시 divergence 플래그(스펙 §3.4).
    """

    id: int | None
    label: str  # 예: "2026-07" (UNIQUE)
    status: RoundStatus
    opened_on: date
    anchor_as_of: date  # 스냅샷 캡처 시 랭킹 effective_as_of = 모델 계열 앵커일
    top20_snapshot: tuple[SnapshotEntry, ...]
    rule_signature: str
    validated: bool
    g7_summary: dict[str, object] | None = None
    carry_in: tuple[CarryInPosition, ...] = ()
    discussion_memo: str | None = None
    top5: tuple[str, ...] = ()  # 확정 Top5 ticker(⊆ top20_snapshot — API 가 검증)
    retrospective: RoundRetrospective | None = None
    performance_snapshot: dict[str, object] | None = None
    closed_at: datetime | None = None
