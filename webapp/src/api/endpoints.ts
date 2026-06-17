/**
 * 엔드포인트별 호출 함수 — 라우트(경로/쿼리)와 응답 타입을 한 곳에 고정.
 *
 * 화면은 이 함수들만 호출하고 URL 문자열을 직접 만들지 않는다(계약 변경 시 여기 한 곳만 수정).
 * 모든 경로는 `src/stockpick/api/` 라우트 실측과 1:1.
 */

import { apiRequest } from "./client";
import type {
  DatasetSummary,
  HealthResponse,
  IngestRequest,
  IngestResult,
  LearningContent,
  LearningTree,
  RankingQuery,
  RankingResponse,
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

export function getLearningTree(signal?: AbortSignal): Promise<LearningTree> {
  return apiRequest<LearningTree>("/api/learning/tree", { signal });
}

export function getLearningContent(path: string, signal?: AbortSignal): Promise<LearningContent> {
  return apiRequest<LearningContent>("/api/learning/content", { query: { path }, signal });
}
