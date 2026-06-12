import type { Grade } from "@/lib/mock/types";

/** 등급 색 체계: A 녹색 → F 적색 일관 단계 (라이트/다크 모두 대응) */
const GRADE_STYLES: Record<Grade, string> = {
  A: "bg-emerald-100 text-emerald-800 ring-emerald-600/25 dark:bg-emerald-500/15 dark:text-emerald-300",
  B: "bg-lime-100 text-lime-800 ring-lime-600/25 dark:bg-lime-500/15 dark:text-lime-300",
  C: "bg-amber-100 text-amber-800 ring-amber-600/25 dark:bg-amber-500/15 dark:text-amber-300",
  D: "bg-orange-100 text-orange-800 ring-orange-600/25 dark:bg-orange-500/15 dark:text-orange-300",
  F: "bg-red-100 text-red-800 ring-red-600/25 dark:bg-red-500/15 dark:text-red-300",
};

const SIZE_STYLES = {
  sm: "h-7 w-7 text-sm rounded-md",
  lg: "h-16 w-16 text-4xl rounded-xl",
} as const;

export default function GradeBadge({
  grade,
  size = "sm",
}: {
  grade: Grade;
  size?: keyof typeof SIZE_STYLES;
}) {
  return (
    <span
      className={`inline-flex items-center justify-center font-bold ring-1 ring-inset ${GRADE_STYLES[grade]} ${SIZE_STYLES[size]}`}
      title={`신뢰성 등급 ${grade}`}
    >
      {grade}
    </span>
  );
}
