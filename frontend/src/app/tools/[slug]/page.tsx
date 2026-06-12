import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import GradeBadge from "@/components/GradeBadge";
import ScoreBar from "@/components/ScoreBar";
import { findToolBySlug, mockTools } from "@/lib/mock/tools";
import { gradeFromScore, type Tool } from "@/lib/mock/types";

export function generateStaticParams() {
  return mockTools.map((t) => ({ slug: t.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const tool = findToolBySlug(slug);
  return { title: tool ? `${tool.name} — 등급 ${tool.grade}` : "도구 상세" };
}

/**
 * 도구 상세 (F4 — 등급 산출 근거 투명성):
 * 등급 히어로 → 축별 점수·근거 → LLM 보정 → 서킷브레이커 보너스 → 버전 메타 → 한계 고지.
 * 근거 펼침은 네이티브 <details> 사용 — 클라이언트 JS 없이 서버 컴포넌트 유지.
 */
export default async function ToolDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const tool = findToolBySlug(slug);
  if (!tool) notFound();

  const base = tool.axisScores.reduce((sum, a) => sum + a.score * a.weight, 0) / 100;
  const bonus = tool.circuitBreakerBonus ? 3 : 0;
  const llmDelta = tool.llmAdjustment?.delta ?? 0;
  const scoreGrade = gradeFromScore(tool.finalScore); // cap 미적용 시의 점수상 등급

  return (
    <div className="space-y-8">
      <GradeHero tool={tool} scoreGrade={scoreGrade} />
      <ScoreBreakdown base={base} bonus={bonus} llmDelta={llmDelta} tool={tool} />
      <AxisSection tool={tool} />
      <LlmAdjustmentCard tool={tool} />
      <CircuitBreakerCard active={tool.circuitBreakerBonus} />
      <AnalysisMeta tool={tool} />
      <DisclaimerNotice />
    </div>
  );
}

function GradeHero({ tool, scoreGrade }: { tool: Tool; scoreGrade: string }) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-start gap-5">
        <GradeBadge grade={tool.grade} size="lg" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{tool.name}</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {tool.description}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
              {tool.category}
            </span>
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 dark:bg-zinc-800">
              {tool.language}
            </span>
            <a
              href={tool.repoUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono underline underline-offset-2 hover:text-zinc-700 dark:hover:text-zinc-200"
            >
              {tool.repoUrl.replace("https://github.com/", "github.com/")}
            </a>
          </div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-bold tabular-nums">
            {tool.finalScore}
            <span className="text-base font-normal text-zinc-400"> / 100</span>
          </div>
          <div className="text-xs text-zinc-500 dark:text-zinc-400">최종 점수</div>
        </div>
      </div>
      {tool.capApplied && (
        <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-700 dark:bg-amber-500/10">
          <p className="font-semibold text-amber-800 dark:text-amber-300">
            치명 위반 등급 상한(cap) 적용 — {tool.capApplied.axis} 축
          </p>
          <p className="mt-1 text-zinc-700 dark:text-zinc-300">
            점수 기준 등급은 {scoreGrade}({tool.finalScore}점)이지만, 치명 위반으로
            등급 상한 {tool.capApplied.maxGrade} 가 적용되었습니다.
          </p>
          <p className="mt-1 text-zinc-600 dark:text-zinc-400">
            사유: {tool.capApplied.reason}
          </p>
        </div>
      )}
    </section>
  );
}

function ScoreBreakdown({
  base,
  bonus,
  llmDelta,
  tool,
}: {
  base: number;
  bonus: number;
  llmDelta: number;
  tool: Tool;
}) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">점수 산출 내역</h2>
      <p className="mt-3 font-mono text-sm">
        규칙 기반 {base}점{bonus > 0 && ` + 서킷 브레이커 보너스 ${bonus}점`}
        {tool.llmAdjustment
          ? ` ${llmDelta >= 0 ? "+" : "−"} LLM 보정 ${Math.abs(llmDelta)}점`
          : " (LLM 보정 미적용)"}{" "}
        = <span className="font-bold">{tool.finalScore}점</span>
      </p>
      <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
        등급 경계: A ≥ 85 · B 70~84 · C 55~69 · D 40~54 · F &lt; 40 — 치명 위반 시
        등급 상한(cap)이 별도 적용됩니다
      </p>
    </section>
  );
}

function AxisSection({ tool }: { tool: Tool }) {
  return (
    <section>
      <h2 className="text-lg font-semibold">축별 점수와 발동 규칙 근거</h2>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        각 축을 클릭하면 점수의 근거가 된 규칙 ID 와 파일/라인이 펼쳐집니다.
      </p>
      <div className="mt-4 space-y-3">
        {tool.axisScores.map((axis) => (
          <details
            key={axis.id}
            className="group rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900"
          >
            <summary className="flex cursor-pointer list-none items-center gap-4 p-4">
              <div className="w-44 shrink-0">
                <span className="font-mono text-xs text-zinc-400">{axis.id}</span>
                <span className="ml-1.5 text-sm font-medium">{axis.label}</span>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  가중치 {axis.weight}
                </div>
              </div>
              <div className="flex-1">
                <ScoreBar score={axis.score} />
              </div>
              <div className="w-14 text-right font-mono text-sm font-semibold tabular-nums">
                {axis.score}
              </div>
              <span className="text-zinc-400 transition-transform group-open:rotate-90">
                ›
              </span>
            </summary>
            <ul className="space-y-2 border-t border-zinc-100 p-4 dark:border-zinc-800">
              {axis.evidences.map((ev, i) => (
                <li key={i} className="text-sm">
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs dark:bg-zinc-800">
                    {ev.ruleId}
                  </span>
                  <span className="ml-2 font-mono text-xs text-zinc-500 dark:text-zinc-400">
                    {ev.file}:{ev.line}
                  </span>
                  <p className="mt-1 text-zinc-700 dark:text-zinc-300">{ev.note}</p>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}

function LlmAdjustmentCard({ tool }: { tool: Tool }) {
  const adj = tool.llmAdjustment;
  if (!adj) {
    return (
      <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-lg font-semibold">LLM 보정</h2>
        <div className="mt-3 inline-flex items-center gap-2 rounded-md bg-zinc-100 px-3 py-1.5 text-sm font-medium dark:bg-zinc-800">
          LLM 보정 미적용
        </div>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          이 등급은 규칙 기반 점수만으로 산출되었습니다. LLM 보정은 호출 실패 또는
          월 예산 한도 도달 시 적용되지 않으며, 등급의 뼈대인 규칙 점수에는 영향이
          없습니다.
        </p>
      </section>
    );
  }
  const positive = adj.delta >= 0;
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">LLM 보정</h2>
        <span
          className={`rounded-md px-2.5 py-1 font-mono text-sm font-bold ${
            positive
              ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300"
              : "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300"
          }`}
        >
          {positive ? "+" : ""}
          {adj.delta}점
        </span>
      </div>
      <p className="mt-3 text-sm text-zinc-700 dark:text-zinc-300">{adj.rationale}</p>
      <div className="mt-4 space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
          인용 근거 (근거 없는 보정은 미적용 처리)
        </h3>
        {adj.citations.map((c, i) => (
          <blockquote
            key={i}
            className="rounded-md border-l-2 border-zinc-300 bg-zinc-50 p-3 dark:border-zinc-600 dark:bg-zinc-800/50"
          >
            <div className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
              {c.file}:{c.line}
            </div>
            <pre className="mt-1 overflow-x-auto font-mono text-xs text-zinc-800 dark:text-zinc-200">
              {c.quote}
            </pre>
          </blockquote>
        ))}
      </div>
      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        보정 범위는 ±10점, 등급 기준 최대 1단계로 제한됩니다 — 등급의 뼈대는 항상
        규칙 점수입니다.
      </p>
    </section>
  );
}

function CircuitBreakerCard({ active }: { active: boolean }) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">서킷 브레이커 (참고 — 등급 축 아님)</h2>
      {active ? (
        <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
          <span className="rounded-md bg-emerald-100 px-2 py-0.5 font-medium text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300">
            탐지됨 — 보너스 +3점
          </span>
          <span className="ml-2 text-zinc-500 dark:text-zinc-400">
            서킷 브레이커 라이브러리 사용이 확인되어 총점에 +3 (상한 100) 반영
          </span>
        </p>
      ) : (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          미탐지 — 보너스 없음. MCP 서버에서 희소한 패턴이라 등급 축이 아닌 가산점으로만
          반영합니다.
        </p>
      )}
    </section>
  );
}

function AnalysisMeta({ tool }: { tool: Tool }) {
  const rows: [string, string][] = [
    ["분석기 버전", tool.versions.analyzer],
    ["프롬프트 버전", tool.versions.prompt],
    ["LLM 모델", tool.versions.model],
    ["분석 대상 commit", tool.commitHash.slice(0, 12)],
    ["분석 일시", tool.analyzedAt.replace("T", " ").replace("Z", " UTC")],
  ];
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-lg font-semibold">분석 메타데이터</h2>
      <dl className="mt-3 grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 sm:justify-start">
            <dt className="w-32 shrink-0 text-zinc-500 dark:text-zinc-400">{label}</dt>
            <dd className="font-mono text-xs leading-5">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function DisclaimerNotice() {
  return (
    <section className="rounded-xl border border-zinc-300 bg-zinc-100 p-6 text-sm dark:border-zinc-700 dark:bg-zinc-800/60">
      <h2 className="font-semibold">자동 분석 한계 고지</h2>
      <p className="mt-2 text-zinc-700 dark:text-zinc-300">
        본 등급은 코드 비실행 정적 자동 분석의 결과이며, 실제 운영 환경에서의 품질과
        안정성을 보장하지 않습니다. 분석 시점의 commit 기준이므로 이후 변경 사항은
        반영되어 있지 않습니다.
      </p>
      <p className="mt-2 text-zinc-700 dark:text-zinc-300">
        등급에 대한 이의 제기·피드백:{" "}
        <a
          href="mailto:appeal@agentgrid.example"
          className="font-medium underline underline-offset-2"
        >
          appeal@agentgrid.example
        </a>{" "}
        <span className="text-zinc-500 dark:text-zinc-400">(placeholder)</span>
      </p>
      <p className="mt-3">
        <Link href="/" className="text-zinc-500 underline underline-offset-2 dark:text-zinc-400">
          ← 디렉토리로 돌아가기
        </Link>
      </p>
    </section>
  );
}
