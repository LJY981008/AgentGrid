import type { Metadata } from "next";
import Link from "next/link";
import { findSubmissionByToken, mockSubmissions } from "@/lib/mock/submissions";
import type { Submission, SubmissionStatus } from "@/lib/mock/types";

export const metadata: Metadata = { title: "제출 상태 추적" };

export function generateStaticParams() {
  return mockSubmissions.map((s) => ({ token: s.token }));
}

const STATUS_STYLES: Record<SubmissionStatus, string> = {
  접수: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  분석중: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  게시: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  실패: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
};

/** 제출 상태 추적 (F1) — 접수 → 분석중 → 게시/실패(사유) 단계 진행 표시 */
export default async function SubmissionStatusPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const submission = findSubmissionByToken(token);

  if (!submission) {
    return (
      <div className="mx-auto max-w-xl rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <h1 className="text-lg font-semibold">추적 토큰을 찾을 수 없습니다</h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          토큰 <span className="font-mono text-xs">{token}</span> 에 해당하는 제출
          이력이 없습니다. 프로토타입에서는 아래 데모 토큰만 조회할 수 있습니다.
        </p>
        <ul className="mt-4 space-y-1.5 text-sm">
          {mockSubmissions.map((s) => (
            <li key={s.token}>
              <Link
                href={`/submissions/${s.token}`}
                className="font-mono text-xs underline underline-offset-2"
              >
                {s.token}
              </Link>
              <span className="ml-2 text-xs text-zinc-500">— {s.status}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return <SubmissionDetail submission={submission} />;
}

function SubmissionDetail({ submission }: { submission: Submission }) {
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">제출 상태 추적</h1>
        <p className="mt-1.5 font-mono text-xs text-zinc-500 dark:text-zinc-400">
          {submission.token}
        </p>
      </div>

      <div className="rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between gap-4">
          <a
            href={submission.repoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="truncate font-mono text-sm underline underline-offset-2"
          >
            {submission.repoUrl.replace("https://github.com/", "github.com/")}
          </a>
          <span
            className={`shrink-0 rounded-md px-2.5 py-1 text-sm font-semibold ${STATUS_STYLES[submission.status]}`}
          >
            {submission.status}
          </span>
        </div>

        <ol className="mt-6 space-y-0">
          {submission.steps.map((step, i) => {
            const isLast = i === submission.steps.length - 1;
            const failed = step.label === "실패";
            return (
              <li key={i} className="relative flex gap-4 pb-6 last:pb-0">
                {!isLast && (
                  <span className="absolute top-3 left-[5px] h-full w-px bg-zinc-200 dark:bg-zinc-700" />
                )}
                <span
                  className={`mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full ${
                    failed
                      ? "bg-red-500"
                      : isLast && submission.status !== "게시"
                        ? "bg-blue-500"
                        : "bg-emerald-500"
                  }`}
                />
                <div>
                  <div className="text-sm font-medium">{step.label}</div>
                  <div className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
                    {step.at.replace("T", " ").replace("Z", " UTC")}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>

        {submission.status === "실패" && submission.failReason && (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-500/10 dark:text-red-300">
            <span className="font-semibold">실패 사유</span>
            <p className="mt-1">{submission.failReason}</p>
          </div>
        )}

        {submission.status === "게시" && submission.toolSlug && (
          <div className="mt-4">
            <Link
              href={`/tools/${submission.toolSlug}`}
              className="inline-block rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
            >
              게시된 상세 페이지 보기 →
            </Link>
          </div>
        )}

        {submission.status === "분석중" && (
          <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
            분석이 진행 중입니다. 이 페이지를 새로고침하면 최신 상태를 확인할 수
            있습니다.
          </p>
        )}
      </div>

      <p className="text-sm">
        <Link
          href="/submit"
          className="text-zinc-500 underline underline-offset-2 dark:text-zinc-400"
        >
          ← 제출 페이지로 돌아가기
        </Link>
      </p>
    </div>
  );
}
