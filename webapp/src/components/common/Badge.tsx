/** 범용 배지 — 상태 색상 구분만. */

import type { ReactNode } from "react";

type Tone = "warn" | "danger" | "ok" | "neutral";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
