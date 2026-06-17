/**
 * 공통 상태 뷰 — 로딩/에러/빈 상태를 한 곳에서 일관 표현.
 *
 * 모든 페이지가 같은 모양으로 로딩·실패·빈 데이터를 보여주도록 한다(1인용 대시보드의 일관성).
 */

import type { ReactNode } from "react";
import { ApiError } from "../../api/client";

export function Loading({ label = "불러오는 중…" }: { label?: string }) {
  return (
    <div className="state-box" role="status" aria-live="polite">
      <div className="spinner" />
      {label}
    </div>
  );
}

/** 에러 박스 — 429(rate limit)·502(업스트림 인증)은 친화 문구로 분기. retry 콜백 있으면 버튼. */
export function ErrorView({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  let friendly = error.message;
  if (error.isRateLimited) {
    friendly = "데이터 소스 호출 한도(무료 20콜/일)를 초과했습니다. 한도 리셋 후 다시 시도하세요.";
  } else if (error.isUpstreamAuth) {
    friendly = "데이터 소스 인증에 실패했습니다(서버 API 키 확인 필요).";
  } else if (error.status === 0) {
    friendly = `${error.message} — API 서버(uvicorn)가 떠 있는지 확인하세요.`;
  }
  return (
    <div className="state-box error" role="alert">
      <div style={{ marginBottom: onRetry ? "0.75rem" : 0 }}>{friendly}</div>
      {onRetry && (
        <button className="btn secondary" onClick={onRetry}>
          다시 시도
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state-box">{children}</div>;
}
