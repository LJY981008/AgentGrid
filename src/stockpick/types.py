"""도메인 계약 타입 원본 — stock-1st_plan §6 / M1 §3 스키마의 코드화 (미국 주식).

⚠️ 2026-06-16 미국 전환(ADR-002): 종목 식별이 한국 6자리 코드 → **CIK(안정 식별자) +
ticker(가격 키, 시변)** 로 변경. 변경 시 기획 문서·M1 스펙과 동기 유지. 순수 도메인은
dataclass, 외부 입력(API 응답·CSV) 검증은 경계에서 별도(pydantic 등, M1 도입). 누락 필드는
추측값 금지 — 명시적 None.

식별자 모델 (ADR-002 — 생존편향 방어 핵심):
- **CIK** = SEC 중앙 인덱스 키. 회사당 영구·재사용 안 함 → 과거-현재 동일성·EDGAR 재무 조인의
  안정 키. 폐지 후에도 불변. 시계열·랭킹·백테스트의 식별 기준은 CIK.
- **ticker** = 거래소 심볼. 가격 데이터(Tiingo/Sharadar)의 조회 키이나 **시변·재사용**됨
  (회사가 심볼 변경, 폐지 후 타사가 동일 ticker 재취득). ticker만으로 과거 동일성을 보장하면
  생존편향·오조인 누수 → CIK 로 앵커링.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Exchange(StrEnum):
    """미국 상장 거래소 구분. 값 = 거래소 코드 문자열.

    StrEnum 사용(`class X(str, Enum)` 아님) — ruff UP042 해소 + 직렬화 시 문자열로 자연 동작.
    종목은 시간에 따라 거래소를 옮길 수 있음(예: NASDAQ→NYSE 이전 상장). Stock.exchange 는
    현재(또는 최종) 거래소이며, 시점별 거래소 이력이 필요하면 별도 이력 테이블로 보강(M2+).
    """

    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    NYSE_AMERICAN = "NYSE_AMERICAN"  # 구 AMEX (소형주)
    NYSE_ARCA = "NYSE_ARCA"  # ETF 주력
    BATS = "BATS"  # Cboe BZX
    OTC = "OTC"  # 장외(폐지 후 강등 등)


@dataclass(frozen=True, slots=True)
class Stock:
    """종목 마스터. 폐지 종목 포함(생존편향 회피 — delisted_at 보존).

    식별: cik = 안정(영구·무재사용) 식별자, ticker = 현재 ticker(시변·재사용 가능). 시계열·랭킹
    조인의 기준 키는 cik. ticker 는 가격 소스 조회용 현재 심볼 — 과거 동일성 보장 불가하므로
    ticker↔cik 매핑 이력은 별도(M1 §3 ticker_history)에서 시점별로 관리한다.
    """

    cik: str  # SEC Central Index Key — 안정 식별자(영구, 재사용 안 함). 보통 10자리 zero-pad
    ticker: str  # 현재 거래소 심볼 — 가격 조회 키(시변·재사용 가능)
    name: str
    exchange: Exchange
    listed_at: date | None
    delisted_at: date | None  # None = 현재 상장 중(생존편향 보존)


@dataclass(frozen=True, slots=True)
class DailyBar:
    """일봉(EOD) OHLCV — 원주가(raw, 미수정) 저장.

    가격 소스(Tiingo/Sharadar)의 조회 키가 ticker 이므로 일봉의 식별 키는 ticker + trade_date.
    수정주가는 adjusted = raw * adj_factor 로 재계산(원본 불변). 수정 기준은 단일 소스
    (Tiingo adjClose / Sharadar closeadj)로 통일하고 액면분할 표본으로 교차검증(M1). 가격은
    Decimal — float 금지(정밀도 BLOCKING, 부동소수 오차로 수익률 왜곡 방지). 누락은 명시적 None.
    """

    ticker: str  # 가격 조회 키(시변) — CIK 와의 시점별 매핑은 ticker_history 로 해소
    trade_date: date
    open: Decimal  # 원주가(미수정)
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    value: int | None  # 거래대금($), 미제공 시 None
    adj_factor: Decimal = Decimal("1")  # 누적조정계수, adjusted = raw*adj_factor (무수정=1)


@dataclass(frozen=True, slots=True)
class TopEntry:
    """Top20/Top5 랭킹 엔트리. score = 정량 룰 산출 점수, rank = 1-based 순위.

    랭킹의 안정 식별 기준은 cik(폐지 종목 포함 백테스트에서 ticker 재사용 오조인 방지). ticker 는
    사람·가격소스 가독성용으로 동반 보존(as_of 시점의 현재 심볼).
    """

    cik: str  # 안정 식별자(백테스트·추적의 조인 기준)
    ticker: str  # as_of 시점 표시용 심볼(가독성·가격 조인)
    exchange: Exchange
    rank: int
    score: float
    # 룰 버전(보정 이력 추적) + 산출 근거(팩터별 기여) — 재현성·투명성
    rule_version: str
    factors: dict[str, float]


@dataclass(frozen=True, slots=True)
class FinancialFact:
    """SEC EDGAR XBRL 재무 단일 fact — companyfacts 직접 파싱 산출(#재무-1, ADR-005).

    M1 §3 financial 설계의 코드화 + concept 차원 추가. 자연키 =
    (cik, concept, fiscal_period, disclosed_at) — 정정공시(amendment)는 같은 회계기간을
    다른 disclosed_at 으로 갖는 **별 행**(원본 보존). PIT(룩어헤드 BLOCKING): 시점 t 결정엔
    `disclosed_at <= t` 인 fact 만 — fiscal_period 말(period_end)이 아니라 공시일
    (EDGAR `filed`)이 기준(재무는 분기말 후 수주~수개월 뒤 공시 — end 기준이면 미래 누설).

    명세 = `docs/apis/sec-edgar/companyfacts.json`(진실 원천). concept = us-gaap/dei 태그
    bare name(예 "StockholdersEquity"·"NetIncomeLoss"·"EntityCommonStockSharesOutstanding").
    value = Decimal(float 금지 — 금액·주식수 정밀). 음수 가능(적자 NetIncomeLoss).
    """

    cik: str  # 안정 식별자(10자리 zero-pad) — ticker→cik 조인 기준
    concept: str  # XBRL 태그 bare name(taxonomy 제외 — 슬라이스 3종은 이름 충돌 없음)
    fiscal_period: str  # fy+fp 라벨(예 "2024-FY"·"2024-Q3") — 연/분기 판별·표시. "-FY"=연간
    period_end: date  # 회계기간 말(EDGAR `end`) — 기간 최신성 정렬 기준(PIT 게이트 아님)
    disclosed_at: date  # EDGAR `filed`(공시일) — PIT 게이트(disclosed_at<=as_of 룩어헤드 차단)
    value: Decimal
