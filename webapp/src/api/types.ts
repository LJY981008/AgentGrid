/**
 * API wire-shape 타입 — `src/stockpick/api/models.py`(pydantic) 의 1:1 미러.
 *
 * ⚠️ 단일 진실 원천은 파이썬 models.py 다. 필드명은 snake_case(서버와 동일), 날짜는
 * ISO `YYYY-MM-DD` 문자열(pydantic 직렬화 결과). 여기서 camelCase 로 바꾸지 않는다 —
 * 서버 계약과 어긋나면 조용한 버그가 생긴다. 계약이 바뀌면 models.py 를 보고 같이 고친다.
 *
 * 비유(Spring): 이 파일이 서버 DTO 의 클라이언트측 미러. 직접 DTO 를 변형하지 않고
 * 응답을 그대로 받아 읽는다(읽기 위주 — 투자 로직/계산은 전부 서버).
 */

// src/stockpick/types.py 의 Exchange(StrEnum) 미러.
export type Exchange =
  | "NYSE"
  | "NASDAQ"
  | "NYSE_AMERICAN"
  | "NYSE_ARCA"
  | "BATS"
  | "OTC";

// ISO 날짜 문자열(YYYY-MM-DD). 가독성용 별칭 — 타입은 string.
export type IsoDate = string;

// --- health ---
export interface HealthResponse {
  status: string;
  version: string;
}

// --- dataset ---
export interface DatasetTicker {
  ticker: string;
  exchange: Exchange;
  row_count: number;
  min_date: IsoDate | null;
  max_date: IsoDate | null;
  source: string | null;
}

export interface DatasetSummary {
  ticker_count: number;
  total_rows: number;
  min_date: IsoDate | null;
  max_date: IsoDate | null;
  sources: string[];
  tickers: DatasetTicker[];
}

// --- ingest ---
export interface IngestTarget {
  ticker: string;
  exchange: Exchange;
}

export interface IngestRequest {
  tickers?: IngestTarget[] | null;
}

export interface TickerIngestResult {
  ticker: string;
  exchange: Exchange;
  bar_count: number;
  min_date: IsoDate | null;
  max_date: IsoDate | null;
  error: string | null;
}

export interface Shortfall {
  ticker: string;
  expected: number;
  actual: number;
}

export interface Verification {
  row_count: number;
  ticker_count: number;
  min_date: string | null;
  max_date: string | null;
  duplicate_count: number;
  nonpositive_adj_factor_count: number;
  nonpositive_price_count: number;
  ohlc_violation_count: number;
  expected_checked: boolean;
  missing_tickers: string[];
  shortfall_tickers: Shortfall[];
  orphan_tickers: string[];
  passed: boolean;
}

export interface IngestResult {
  passed: boolean;
  total_rows: number;
  ingested_ticker_count: number;
  empty_tickers: string[];
  failed_tickers: string[];
  results: TickerIngestResult[];
  verification: Verification | null;
}

// --- ranking (§4.1 미검증 경고 필수) ---
export interface TopEntry {
  cik: string;
  ticker: string;
  exchange: Exchange;
  rank: number;
  score: number;
  rule_version: string;
  factors: Record<string, number>;
}

export interface RankingParams {
  lookback_days: number;
  skip_recent_days: number;
  top_n: number;
  group: string; // "exchange" | "all"
}

export interface RankingMeta {
  validated: boolean; // 항상 false — 백테스트 검증 전 룰은 알파 아님
  warning: string;
  as_of: IsoDate | null;
  params: RankingParams;
  unrankable_tickers: string[];
}

export interface RankingResponse {
  entries: TopEntry[];
  meta: RankingMeta;
}

// 랭킹 쿼리 파라미터(GET /api/ranking).
export interface RankingQuery {
  as_of?: IsoDate;
  lookback_days?: number;
  skip_recent_days?: number;
  top_n?: number;
  group?: "exchange" | "all";
}

// --- learning ---
export interface LearningNode {
  name: string;
  path: string; // docs/learning 기준 상대경로
  type: "dir" | "file";
  children: LearningNode[];
}

export interface LearningTree {
  root: LearningNode[];
}

export interface LearningContent {
  path: string; // 요청 경로(상대)
  dir: string; // 문서가 속한 디렉토리(상대) — 상대 이미지 URL 재작성 기준
  content: string; // 마크다운 원문(렌더는 프론트)
}
