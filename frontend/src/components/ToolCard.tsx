import Link from "next/link";
import GradeBadge from "@/components/GradeBadge";
import type { Tool } from "@/lib/mock/types";

/** 디렉토리 목록 카드 — 이름/설명/등급/카테고리/언어/최근 분석일 (F3 수용 기준) */
export default function ToolCard({ tool }: { tool: Tool }) {
  return (
    <Link
      href={`/tools/${tool.slug}`}
      className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 transition-colors hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-600"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-semibold">{tool.name}</h3>
          <p className="mt-1 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
            {tool.description}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <GradeBadge grade={tool.grade} />
          {tool.capApplied && (
            <span
              className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300"
              title={`치명 위반으로 등급 상한 ${tool.capApplied.maxGrade} 적용`}
            >
              cap
            </span>
          )}
        </div>
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
          {tool.category}
        </span>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
          {tool.language}
        </span>
        <span className="ml-auto">분석 {tool.analyzedAt.slice(0, 10)}</span>
      </div>
    </Link>
  );
}
