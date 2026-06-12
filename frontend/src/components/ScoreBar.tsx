/** 축 점수 시각화 바 — 70 이상 녹색 / 40~69 황색 / 40 미만 적색 */
export default function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 70 ? "bg-emerald-500" : score >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="h-2 w-full rounded-full bg-zinc-200 dark:bg-zinc-800">
      <div
        className={`h-2 rounded-full ${color}`}
        style={{ width: `${Math.max(score, 0)}%` }}
      />
    </div>
  );
}
