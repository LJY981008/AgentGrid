import type { Metadata } from "next";
import Link from "next/link";
import SubmitForm from "@/components/SubmitForm";
import { mockSubmissions } from "@/lib/mock/submissions";

export const metadata: Metadata = { title: "도구 제출" };

/**
 * 제출 화면 (F1) — 폼 인터랙션만 SubmitForm("use client").
 * 하단의 데모 토큰 목록은 프로토타입 평가용 — 4가지 상태 화면을 바로 확인할 수 있다.
 */
export default function SubmitPage() {
  return (
    <div className="mx-auto max-w-xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">MCP 서버 제출</h1>
        <p className="mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">
          GitHub 저장소 URL 을 제출하면 자동 분석을 거쳐 신뢰성 등급과 산출 근거가
          디렉토리에 게시됩니다. 로그인 없이 제출할 수 있습니다.
        </p>
      </div>

      <SubmitForm />

      <div className="rounded-lg border border-dashed border-zinc-300 p-4 dark:border-zinc-700">
        <h2 className="text-sm font-semibold">프로토타입 데모 — 상태 추적 예시</h2>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          백엔드 미연동 상태의 평가용 링크입니다. 4가지 제출 상태 화면을 바로 볼 수
          있습니다.
        </p>
        <ul className="mt-3 space-y-1.5 text-sm">
          {mockSubmissions.map((s) => (
            <li key={s.token}>
              <Link
                href={`/submissions/${s.token}`}
                className="font-mono text-xs underline underline-offset-2"
              >
                {s.token}
              </Link>
              <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                — {s.status}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
