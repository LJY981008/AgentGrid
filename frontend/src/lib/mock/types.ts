/**
 * Mock 도메인 타입 — docs/plans/2nd_plan.md §4(지표 정의)를 충실히 반영.
 * 추후 백엔드 DTO 계약(ApiResult<T> payload) 초안이 된다.
 */

export type Category = "DB 연동" | "API 연동" | "브라우저 제어" | "기타";
export type Language = "TypeScript" | "Python";
export type Grade = "A" | "B" | "C" | "D" | "F";
export type AxisId = "R1" | "R2" | "R3" | "R4" | "R5" | "R6";

/** 규칙 발동 근거 — 2nd_plan §4.1 원칙 4: 모든 점수는 규칙 ID + 파일/라인과 함께 공개 */
export interface Evidence {
  ruleId: string;
  file: string;
  line: number;
  note: string;
}

/** 축별 점수 — 가중치: R1 25 / R2 20 / R3 15 / R4 15 / R5 15 / R6 10 (2nd_plan §4.2 초안) */
export interface AxisScore {
  id: AxisId;
  label: string;
  score: number; // 0~100
  weight: number;
  evidences: Evidence[];
}

/** 치명 위반 등급 상한 — 예: 외부 호출 존재 + 타임아웃 0건 → 최대 C (2nd_plan §4.3 R2) */
export interface CapApplied {
  axis: AxisId;
  reason: string;
  maxGrade: Grade;
}

/** LLM 보정 인용 근거 — 가드레일 #4: 근거 없는 보정은 미적용 처리 (3rd_plan §1.2) */
export interface LlmCitation {
  file: string;
  line: number;
  quote: string;
}

/** LLM 보정 — delta ∈ [-10, +10], 등급 기준 최대 1단계 (가드레일 #1) */
export interface LlmAdjustment {
  delta: number;
  rationale: string;
  citations: LlmCitation[];
}

/** 버전 3종 기록 — 가드레일 #3: 분석기/프롬프트/모델 버전을 모든 등급 레코드에 (3rd_plan §1.1·§1.2) */
export interface AnalysisVersions {
  analyzer: string;
  prompt: string;
  model: string;
}

export interface Tool {
  slug: string;
  name: string;
  description: string;
  category: Category;
  language: Language;
  repoUrl: string;
  grade: Grade;
  /** final = clamp(base + bonus + llm_adj, 0, 100) — 2nd_plan §4.4 */
  finalScore: number;
  axisScores: AxisScore[];
  capApplied: CapApplied | null;
  /** 서킷 브레이커 탐지 시 +3 보너스 (등급 축 아님 — 2nd_plan §4.2 제외 항목) */
  circuitBreakerBonus: boolean;
  /** null = "LLM 보정 미적용" (예산 소진/호출 실패 — 가드레일 #6 실패 격리) */
  llmAdjustment: LlmAdjustment | null;
  versions: AnalysisVersions;
  commitHash: string;
  analyzedAt: string; // ISO 8601
}

/** 제출 상태 — F1: 접수 → 분석중 → 게시/실패(사유) */
export type SubmissionStatus = "접수" | "분석중" | "게시" | "실패";

export interface SubmissionStep {
  label: SubmissionStatus;
  at: string; // ISO 8601
}

export interface Submission {
  token: string;
  repoUrl: string;
  status: SubmissionStatus;
  failReason?: string;
  /** 게시 완료 시 연결되는 도구 상세 */
  toolSlug?: string;
  steps: SubmissionStep[];
}

/** 등급 경계 (2nd_plan §4.4 초안): A ≥ 85 | B 70~84 | C 55~69 | D 40~54 | F < 40 */
export function gradeFromScore(score: number): Grade {
  if (score >= 85) return "A";
  if (score >= 70) return "B";
  if (score >= 55) return "C";
  if (score >= 40) return "D";
  return "F";
}

/** 정렬용 등급 순위 (A 가 가장 높음) */
export const GRADE_RANK: Record<Grade, number> = { A: 0, B: 1, C: 2, D: 3, F: 4 };
