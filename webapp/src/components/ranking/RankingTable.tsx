/**
 * 랭킹 표 — 거래소별 블록 렌더(group=exchange 시 거래소마다 rank 1부터) + score 바.
 *
 * ⚠️ 표시만 한다. 정렬·순위는 서버가 준 rank 를 그대로 신뢰(프론트 재정렬 금지 — 서버 단일 진실).
 * score 바는 그룹 내 최대 score 대비 width%(순수 CSS, Recharts 미설치). 점수 비교는 같은
 * 그룹·같은 룰버전 안에서만 의미 — 그래서 그룹별로 max 를 따로 잡는다.
 */

import type { TopEntry } from "../../api/types";
import { fmtNum } from "../../lib/format";

/** 거래소(또는 'ALL')별로 엔트리를 묶는다. group=all 이면 rank 가 전역 1..N 이라 단일 블록. */
function groupEntries(entries: TopEntry[], groupByExchange: boolean): [string, TopEntry[]][] {
  if (!groupByExchange) return [["전체", entries]];
  const map = new Map<string, TopEntry[]>();
  for (const e of entries) {
    const arr = map.get(e.exchange) ?? [];
    arr.push(e);
    map.set(e.exchange, arr);
  }
  // 각 블록은 rank 오름차순(서버가 이미 그렇게 주지만 방어적으로 정렬 — 값 변경 아님).
  for (const arr of map.values()) arr.sort((a, b) => a.rank - b.rank);
  return [...map.entries()];
}

function RankRow({ entry, maxScore }: { entry: TopEntry; maxScore: number }) {
  // 음수 score 도 가능(모멘텀). 막대는 0..max 범위로 클램프해 길이만 표현(비교 보조용).
  const pct = maxScore > 0 ? Math.max(0, Math.min(100, (entry.score / maxScore) * 100)) : 0;
  return (
    <li className="rank-row">
      <span className="rank-num">{entry.rank}</span>
      <span>
        <span className="rank-ticker">{entry.ticker}</span>{" "}
        <span className="rank-meta">
          {entry.exchange} · {entry.rule_version}
        </span>
      </span>
      <span className="rank-score">
        <span className="num">{fmtNum(entry.score)}</span>
      </span>
      <span className="score-bar-track" aria-hidden>
        <span className="score-bar-fill" style={{ width: `${pct}%` }} />
      </span>
    </li>
  );
}

export function RankingTable({
  entries,
  groupByExchange,
}: {
  entries: TopEntry[];
  groupByExchange: boolean;
}) {
  const groups = groupEntries(entries, groupByExchange);
  return (
    <div>
      {groups.map(([label, group]) => {
        const maxScore = group.reduce((m, e) => Math.max(m, e.score), 0);
        return (
          <section key={label}>
            {groupByExchange && (
              <div className="group-head">
                <span>{label}</span>
                <span>· 상위 {group.length}</span>
              </div>
            )}
            <ul className="rank-list">
              {group.map((e) => (
                <RankRow key={`${e.exchange}-${e.cik || e.ticker}-${e.rank}`} entry={e} maxScore={maxScore} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
