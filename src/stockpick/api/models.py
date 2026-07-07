"""API 응답·요청 계약(pydantic) — 프론트(Vite+React PWA)가 소비할 wire-shape 의 단일 출처.

⚠️ 이 파일이 프론트 TypeScript 타입의 진실 원천이다. 필드명은 snake_case(파이썬 도메인과 일치),
날짜는 ISO `YYYY-MM-DD` 문자열로 직렬화한다(pydantic 이 `datetime.date` → ISO 문자열 자동).
도메인 dataclass(types.py)와의 차이: 여기 모델은 **경계 검증·직렬화 전용**이며, 내부 계산 타입을
그대로 노출하지 않고 프론트가 읽기 쉬운 평탄 구조로 매핑한다(예: VerificationReport 의
shortfall_tickers (ticker, expected, actual) 튜플 → 명시적 객체).

금융 BLOCKING 연계(§4.1): RankingResponse.meta 는 `validated=false` + warning 을 **항상** 포함
한다(백테스트 검증 전 룰은 알파 아님 — 프론트가 경고 배지를 상시 표시하도록 계약에 못박음).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from ..types import Exchange

# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """GET /api/health — 생존 신호 + 패키지 버전."""

    status: str = "ok"
    version: str  # importlib.metadata.version("stockpick"), 실패 시 "unknown"


# ---------------------------------------------------------------------------
# dataset (적재 Parquet 요약)
# ---------------------------------------------------------------------------


class DatasetTicker(BaseModel):
    """적재 데이터셋의 ticker 1건 요약(DuckDB 집계)."""

    ticker: str
    exchange: Exchange
    row_count: int
    min_date: date | None
    max_date: date | None
    source: str | None


class DatasetSummary(BaseModel):
    """GET /api/dataset — 적재된 data/parquet 트리 요약. 빈 트리면 모든 카운트 0(200, 에러 아님)."""

    ticker_count: int
    total_rows: int
    min_date: date | None
    max_date: date | None
    sources: list[str]
    tickers: list[DatasetTicker]


# ---------------------------------------------------------------------------
# ingest (라이브 EODHD 수집)
# ---------------------------------------------------------------------------


class IngestTarget(BaseModel):
    """수집 대상 1건. exchange 는 Exchange enum 검증(알 수 없는 값 → 422, 추측 매핑 금지)."""

    ticker: str = Field(min_length=1)
    exchange: Exchange


class IngestRequest(BaseModel):
    """POST /api/ingest 요청. tickers=null/생략 → 서버 데모 유니버스(9종목)."""

    tickers: list[IngestTarget] | None = None


class TickerIngestResultModel(BaseModel):
    """종목 1건 적재 결과. bar_count=0 + error=null 이면 데이터 부족(소스 빈 결과 — 명시)."""

    ticker: str
    exchange: Exchange
    bar_count: int
    min_date: date | None
    max_date: date | None
    error: str | None


class ShortfallModel(BaseModel):
    """기대보다 실제 행수가 적은 종목(부분 소실 — 게이트 실패 근거). 튜플 평탄화."""

    ticker: str
    expected: int
    actual: int


class VerificationModel(BaseModel):
    """적재 무결성 검증 리포트(생존편향 소실 게이트 결과)."""

    row_count: int
    ticker_count: int
    min_date: str | None
    max_date: str | None
    duplicate_count: int
    nonpositive_adj_factor_count: int
    nonpositive_price_count: int
    ohlc_violation_count: int
    expected_checked: bool
    missing_tickers: list[str]
    shortfall_tickers: list[ShortfallModel]
    orphan_tickers: list[str]
    passed: bool


class IngestResult(BaseModel):
    """POST /api/ingest 응답 — IngestSummary 매핑. report=null 이면 적재 0종목(검증 트리 없음)."""

    passed: bool
    total_rows: int
    ingested_ticker_count: int
    empty_tickers: list[str]
    failed_tickers: list[str]
    results: list[TickerIngestResultModel]
    verification: VerificationModel | None


# ---------------------------------------------------------------------------
# ranking (Top 랭킹 — §4.1 미검증 경고 필수)
# ---------------------------------------------------------------------------


class TopEntryModel(BaseModel):
    """랭킹 엔트리 1건. cik = EDGAR 저장본으로 해소(#2, 미해소 ticker 는 빈 문자열).

    factors = 산출 근거 dict. 기본 `momentum`, 재무 적재 시 `roe`(퀄리티)·`pb`(밸류) 추가
    (#재무-1 — 미해소·결측 키는 생략). ⚠️ rank·score 는 모멘텀만 — 재무는 결합·가중 안 함
    (§9-2, factors 는 정보 노출). 노출이 검증을 뜻하지 않음(meta.validated=false 불변).
    """

    cik: str
    ticker: str
    exchange: Exchange
    rank: int
    score: float
    rule_version: str
    factors: dict[str, float]


class RankingParams(BaseModel):
    """랭킹 산출에 사용된 파라미터(재현성·프론트 표시)."""

    lookback_days: int
    skip_recent_days: int
    top_n: int
    group: str  # "exchange" | "all"


class RankingMeta(BaseModel):
    """랭킹 메타 — ⚠️ validated=false + warning 항상 포함(§4.1 BLOCKING, 프론트 경고 배지)."""

    validated: bool  # 항상 False — 백테스트 검증 전 룰은 알파 아님
    warning: str
    as_of: date | None  # 데이터 없으면 null
    params: RankingParams
    unrankable_tickers: list[str]  # score=None(데이터 부족) — 조용한 누락 금지


class RankingResponse(BaseModel):
    """GET /api/ranking 응답. 빈 데이터면 entries=[], meta.as_of=null, warning 유지(200)."""

    entries: list[TopEntryModel]
    meta: RankingMeta


# ---------------------------------------------------------------------------
# backtest (백테스트 — §4.1 미검증 경고 필수, 골격 데이터)
# ---------------------------------------------------------------------------


class EquityPoint(BaseModel):
    """자산곡선 한 점. value=누적 자산(시작 1.0 기준). Decimal→float 직렬화 경계."""

    date: date
    value: float


class BacktestParams(BaseModel):
    """백테스트 산출에 사용된 파라미터(재현성·프론트 표시). cost/lookback 등은 서버 고정값 노출."""

    strategy: str  # "equal_weight" | "score_weight"
    top_n: int
    rebalance_freq: str  # "monthly" | "quarterly"
    lookback_days: int
    skip_recent_days: int
    cost_bps: float
    delisting_recovery_rate: float


class BacktestMetrics(BaseModel):
    """백테스트 지표. 돈/수익은 내부 Decimal → 직렬화 경계에서 float(통계는 본래 float)."""

    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    turnover: float
    total_cost: float
    n_rebalances: int
    n_delisted_liquidations: int  # 폐지 청산 건수(생존편향 가드 발동 증거)


class BacktestMeta(BaseModel):
    """백테스트 메타 — ⚠️ validated=false + warning 항상(§4.1). data_caveats 로 골격 한계 고지."""

    validated: bool  # 항상 False — 골격·미검증(결제+S6 게이트 전)
    warning: str
    params: BacktestParams
    data_caveats: list[str]  # survivorship(가격기반 유니버스)·cik 미해소·구간 짧음 등


class BacktestResponse(BaseModel):
    """GET /api/backtest 응답. 빈 데이터면 곡선=[], 지표 0, warning 유지(200, 에러 아님)."""

    equity_curve: list[EquityPoint]  # 전략 자산곡선
    benchmark_curve: list[EquityPoint]  # 등가중 유니버스 벤치(차트 오버레이)
    metrics: BacktestMetrics
    benchmark_returns: dict[str, float]  # {"EQUAL_WEIGHT_UNIVERSE": 총수익}
    meta: BacktestMeta


# ---------------------------------------------------------------------------
# learning (docs/learning 학습노트)
# ---------------------------------------------------------------------------


class LearningNode(BaseModel):
    """학습 트리 노드(재귀). type=dir 이면 children, type=file 이면 잎."""

    name: str
    path: str  # docs/learning 기준 상대경로(슬래시 구분)
    type: str  # "dir" | "file"
    children: list[LearningNode] = Field(default_factory=list)


class LearningTree(BaseModel):
    """GET /api/learning/tree — docs/learning 디렉토리 스캔 트리(마크다운 파일만 잎으로)."""

    root: list[LearningNode]


class LearningContent(BaseModel):
    """GET /api/learning/content — 마크다운 원문 + dir(이미지 상대경로 재작성 기준)."""

    path: str  # 요청 경로(상대)
    dir: str  # 이 문서가 속한 디렉토리(상대) — 프론트가 상대 이미지 URL 재작성에 사용
    content: str  # 마크다운 원문(렌더는 프론트 책임)


# ── 추적·보정 루프(M4) — 라운드·거래·성과 계약(스펙 §6) ─────────────────────
# 돈 필드는 API 표시용 float 변환(계산·영속은 Decimal — tracking/repo 책임). 동결 스냅샷은
# repo 가 Decimal→str 로 저장(정밀도 보존). return_convention 필수 = 무표기 척도 혼합 차단.


class SnapshotEntryModel(BaseModel):
    """라운드 생성 시점 Top20 1행(동결 표시용)."""

    cik: str
    ticker: str
    exchange: str
    rank: int
    score: float
    factors: dict[str, float] = Field(default_factory=dict)
    anchor_close: float | None = None


class CarryInModel(BaseModel):
    ticker: str
    quantity: float
    anchor_close: float | None = None


class RetrospectiveModel(BaseModel):
    """구조화 회고(close 필수) — outcome 아닌 process 채점 유도 3필드."""

    judgment_good: str = Field(min_length=5, description="잘한 판단(근거 포함)")
    judgment_bad: str = Field(min_length=5, description="잘못한 판단(근거 포함)")
    rule_change: str = Field(min_length=2, description="다음 라운드 규칙 변경(없으면 '없음')")


class RoundCreateRequest(BaseModel):
    label: str = Field(min_length=1, description="라운드 라벨(예: 2026-07·UNIQUE)")
    as_of: date | None = Field(default=None, description="스냅샷 평가 시점(미지정=최신 거래일)")


class Top5Request(BaseModel):
    memo: str = Field(min_length=5, description="Claude 토의 요약(선정 근거)")
    top5: list[str] = Field(min_length=1, max_length=5, description="확정 종목(⊆ Top20)")


class TradeCreateRequest(BaseModel):
    ticker: str = Field(min_length=1)
    side: Literal["BUY", "SELL"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fee: Decimal = Field(default=Decimal(0), ge=0)
    executed_on: date
    note: str | None = None


class CashFlowCreateRequest(BaseModel):
    amount: Decimal = Field(description="입금 +, 출금 −(0 금지)")
    flowed_on: date
    note: str | None = None


class VoidRequest(BaseModel):
    reason: str = Field(min_length=2, description="void 사유(감사 추적)")


class TradeModel(BaseModel):
    id: int
    round_id: int
    ticker: str
    side: str
    quantity: float
    price: float
    fee: float
    executed_on: date
    note: str | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None


class CashFlowModel(BaseModel):
    id: int
    round_id: int
    amount: float
    flowed_on: date
    note: str | None = None
    voided_at: datetime | None = None


class RoundModel(BaseModel):
    """라운드 상세 — 스냅샷·validated 맥락 동결 표시(당시 값·미래 룰 검증과 무관)."""

    id: int
    label: str
    status: str
    opened_on: date
    anchor_as_of: date
    rule_signature: str
    validated: bool
    warning: str
    top20: list[SnapshotEntryModel]
    carry_in: list[CarryInModel] = Field(default_factory=list)
    discussion_memo: str | None = None
    top5: list[str] = Field(default_factory=list)
    retrospective: RetrospectiveModel | None = None
    closed_at: datetime | None = None
    trades: list[TradeModel] = Field(default_factory=list)
    cash_flows: list[CashFlowModel] = Field(default_factory=list)


class RoundListItem(BaseModel):
    id: int
    label: str
    status: str
    opened_on: date
    closed_at: datetime | None = None


class PerfPoint(BaseModel):
    day: date
    value: float


class SeriesPerfModel(BaseModel):
    cumulative_return: float
    max_drawdown: float
    index: list[PerfPoint] = Field(default_factory=list)
    unmeasurable: list[str] = Field(default_factory=list)


class ContributionModel(BaseModel):
    ticker: str
    pnl: float


class SlippageModel(BaseModel):
    trade_id: int | None
    ticker: str
    side: str
    exec_price: float
    day_close: float | None
    cost_pct: float | None


class PerformanceResponse(BaseModel):
    """4계열+파생 — 전 계열 price return(배당 미반영) 명시·공통 as-of 절단·판정유보 라벨."""

    as_of: date
    stale: bool
    return_convention: Literal["price"]
    actual: SeriesPerfModel
    top5_model: SeriesPerfModel
    top20_model: SeriesPerfModel
    spy: SeriesPerfModel
    selection_effect: float
    execution_effect: float
    contributions: list[ContributionModel]
    slippages: list[SlippageModel]
    hit_rate: float | None
    n_picks_cumulative: int
    verdict_deferred: bool
    liquidated: list[str] = Field(default_factory=list)
    validated: bool
    warning: str


class BenchmarkSyncResponse(BaseModel):
    price_rows: int
    split_events: int
