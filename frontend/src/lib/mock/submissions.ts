import type { Submission } from "./types";

/**
 * Mock 제출 4건 — F1 수용 기준의 4상태(접수/분석중/게시/실패) 각 1건.
 * 제출 폼은 실제 저장 없이 RECEIVED_TOKEN 을 발급해 상태 추적 플로우를 시연한다.
 */
export const mockSubmissions: Submission[] = [
  {
    token: "sub-rcv-7f3a9c",
    repoUrl: "https://github.com/example-dev/my-mcp-server",
    status: "접수",
    steps: [{ label: "접수", at: "2026-06-12T10:02:00Z" }],
  },
  {
    token: "sub-run-2b8e1d",
    repoUrl: "https://github.com/example-dev/vector-search-mcp",
    status: "분석중",
    steps: [
      { label: "접수", at: "2026-06-12T09:14:00Z" },
      { label: "분석중", at: "2026-06-12T09:15:30Z" },
    ],
  },
  {
    token: "sub-pub-9c4f2a",
    repoUrl: "https://github.com/acme-labs/postgres-mcp",
    status: "게시",
    toolSlug: "postgres-mcp",
    steps: [
      { label: "접수", at: "2026-06-10T14:01:00Z" },
      { label: "분석중", at: "2026-06-10T14:02:10Z" },
      { label: "게시", at: "2026-06-10T14:22:00Z" },
    ],
  },
  {
    token: "sub-fail-5d1e8b",
    repoUrl: "https://github.com/example-dev/go-files-mcp",
    status: "실패",
    failReason:
      "지원하지 않는 언어(Go) — MVP 는 TypeScript/Python 만 분석합니다 (확정 결정 #3). 지원 언어로 재작성 후 재제출해 주세요.",
    steps: [
      { label: "접수", at: "2026-06-11T17:40:00Z" },
      { label: "분석중", at: "2026-06-11T17:41:20Z" },
      { label: "실패", at: "2026-06-11T17:43:05Z" },
    ],
  },
];

/** 제출 폼이 mock 발급하는 추적 토큰 (접수 상태 케이스로 연결) */
export const RECEIVED_TOKEN = "sub-rcv-7f3a9c";

export function findSubmissionByToken(token: string): Submission | undefined {
  return mockSubmissions.find((s) => s.token === token);
}
