/**
 * 엔드포인트별 호출 함수 — 라우트(경로/쿼리)와 응답 타입을 한 곳에 고정.
 *
 * 화면은 이 함수들만 호출하고 URL 문자열을 직접 만들지 않는다(계약 변경 시 여기 한 곳만 수정).
 * 모든 경로는 `src/stockpick/api/` 라우트 실측과 1:1.
 */

import { apiRequest } from "./client";
import type {
  BacktestQuery,
  BacktestResponse,
  BenchmarkSyncResult,
  CashFlowCreate,
  CashFlowItem,
  DatasetSummary,
  HealthResponse,
  IngestRequest,
  IngestResult,
  LearningContent,
  LearningTree,
  Performance,
  RankingQuery,
  RankingResponse,
  Retrospective,
  Round,
  RoundListItem,
  TradeCreate,
  TradeItem,
} from "./types";

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/api/health", { signal });
}

export function getDataset(signal?: AbortSignal): Promise<DatasetSummary> {
  return apiRequest<DatasetSummary>("/api/dataset", { signal });
}

export function getRanking(q: RankingQuery = {}, signal?: AbortSignal): Promise<RankingResponse> {
  return apiRequest<RankingResponse>("/api/ranking", {
    query: {
      as_of: q.as_of,
      lookback_days: q.lookback_days,
      skip_recent_days: q.skip_recent_days,
      top_n: q.top_n,
      group: q.group,
    },
    signal,
  });
}

/**
 * 라이브 EODHD 수집 트리거. body.tickers 생략/null → 서버 데모 9종목.
 * ⚠️ 무료 티어(20콜/일) 소비 — 호출부에서 사용자 고지 필수. 429=한도, 502=업스트림 인증.
 */
export function postIngest(req: IngestRequest = {}, signal?: AbortSignal): Promise<IngestResult> {
  return apiRequest<IngestResult>("/api/ingest", {
    method: "POST",
    body: { tickers: req.tickers ?? null },
    signal,
  });
}

/**
 * 룰 백테스트(골격) — 자산곡선·지표·벤치. ⚠️ meta.validated=false 상시(미검증 — 알파 아님).
 * 쿼리는 strategy·top_n·rebalance_freq 만(나머지 서버 고정 — 과적합 노브 최소화).
 */
export function getBacktest(
  q: BacktestQuery = {},
  signal?: AbortSignal,
): Promise<BacktestResponse> {
  return apiRequest<BacktestResponse>("/api/backtest", {
    query: {
      strategy: q.strategy,
      top_n: q.top_n,
      rebalance_freq: q.rebalance_freq,
    },
    signal,
  });
}

export function getLearningTree(signal?: AbortSignal): Promise<LearningTree> {
  return apiRequest<LearningTree>("/api/learning/tree", { signal });
}

export function getLearningContent(path: string, signal?: AbortSignal): Promise<LearningContent> {
  return apiRequest<LearningContent>("/api/learning/content", { query: { path }, signal });
}

// --- tracking (M4 추적·보정 루프) ---

export function getRounds(signal?: AbortSignal): Promise<RoundListItem[]> {
  return apiRequest<RoundListItem[]>("/api/rounds", { signal });
}

export function getRound(id: number, signal?: AbortSignal): Promise<Round> {
  return apiRequest<Round>(`/api/rounds/${id}`, { signal });
}

export function postRound(label: string, signal?: AbortSignal): Promise<Round> {
  return apiRequest<Round>("/api/rounds", { method: "POST", body: { label }, signal });
}

export function patchTop5(
  id: number,
  memo: string,
  top5: string[],
  signal?: AbortSignal,
): Promise<Round> {
  return apiRequest<Round>(`/api/rounds/${id}`, { method: "PATCH", body: { memo, top5 }, signal });
}

export function postTrade(id: number, body: TradeCreate, signal?: AbortSignal): Promise<TradeItem> {
  return apiRequest<TradeItem>(`/api/rounds/${id}/trades`, { method: "POST", body, signal });
}

export function postCashFlow(
  id: number,
  body: CashFlowCreate,
  signal?: AbortSignal,
): Promise<CashFlowItem> {
  return apiRequest<CashFlowItem>(`/api/rounds/${id}/cash-flows`, {
    method: "POST",
    body,
    signal,
  });
}

export function postVoidTrade(
  tradeId: number,
  reason: string,
  signal?: AbortSignal,
): Promise<TradeItem> {
  return apiRequest<TradeItem>(`/api/trades/${tradeId}/void`, {
    method: "POST",
    body: { reason },
    signal,
  });
}

export function getPerformance(id: number, signal?: AbortSignal): Promise<Performance> {
  return apiRequest<Performance>(`/api/rounds/${id}/performance`, { signal });
}

export function postCloseRound(
  id: number,
  retro: Retrospective,
  signal?: AbortSignal,
): Promise<Round> {
  return apiRequest<Round>(`/api/rounds/${id}/close`, { method: "POST", body: retro, signal });
}

export function postBenchmarkSync(signal?: AbortSignal): Promise<BenchmarkSyncResult> {
  return apiRequest<BenchmarkSyncResult>("/api/benchmark/sync", { method: "POST", signal });
}
