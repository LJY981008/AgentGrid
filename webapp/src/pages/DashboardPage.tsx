/**
 * 홈 — Top 랭킹 대시보드.
 *
 * §4.1 BLOCKING: 미검증 경고 배너 **상시**(UnvalidatedWarning, fail-safe). 빈 데이터(첫 실행)면
 * "데이터 수집 먼저" 안내 + DataPage 유도 — 수집 없이는 랭킹이 없다. 그룹 토글(거래소별/전체)은
 * 표시 옵션일 뿐 서버 재계산을 요청한다(group 파라미터 → 서버가 다시 랭킹, 프론트는 계산 안 함).
 */

import { useState } from "react";
import { Link } from "react-router";
import { getRanking } from "../api/endpoints";
import { useApi } from "../api/useApi";
import type { RankingQuery } from "../api/types";
import { ErrorView, Loading } from "../components/common/StateViews";
import { UnvalidatedWarning } from "../components/common/UnvalidatedWarning";
import { RankingTable } from "../components/ranking/RankingTable";
import { fmtDate } from "../lib/format";

export function DashboardPage() {
  const [group, setGroup] = useState<"exchange" | "all">("exchange");
  const query: RankingQuery = { group, top_n: 5 };
  const { data, loading, error, refetch } = useApi(
    (signal) => getRanking(query, signal),
    [group],
  );

  return (
    <div>
      <header className="page-head">
        <h1>Top 랭킹</h1>
        <p>정량 룰 기반 모멘텀 상위 종목. 보정·토의 전 1차 후보입니다.</p>
      </header>

      {/* 경고는 데이터 유무·로딩·에러와 무관하게 항상 먼저(누락 시에도 노출되도록). */}
      <UnvalidatedWarning validated={data?.meta.validated} warning={data?.meta.warning} />

      <div className="card">
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
          <button
            className={group === "exchange" ? "btn" : "btn secondary"}
            onClick={() => setGroup("exchange")}
          >
            거래소별
          </button>
          <button
            className={group === "all" ? "btn" : "btn secondary"}
            onClick={() => setGroup("all")}
          >
            전체
          </button>
        </div>

        {loading && <Loading label="랭킹 산출 중…" />}
        {error && <ErrorView error={error} onRetry={refetch} />}

        {data && !loading && !error && (
          <>
            {data.entries.length === 0 ? (
              <div className="state-box">
                <p style={{ marginTop: 0 }}>아직 적재된 데이터가 없어 랭킹을 만들 수 없습니다.</p>
                <p>
                  먼저 <Link to="/data">데이터 페이지</Link>에서 종목을 수집하세요.
                </p>
              </div>
            ) : (
              <>
                <div className="rank-meta" style={{ marginBottom: "0.5rem" }}>
                  기준일 {fmtDate(data.meta.as_of)} · 룩백 {data.meta.params.lookback_days}일 · 최근{" "}
                  {data.meta.params.skip_recent_days}일 제외
                </div>
                <RankingTable
                  entries={data.entries}
                  groupByExchange={data.meta.params.group === "exchange"}
                />
                {data.meta.unrankable_tickers.length > 0 && (
                  <div className="notice" style={{ marginTop: "0.75rem" }}>
                    산출 불가(데이터 부족) {data.meta.unrankable_tickers.length}종목:{" "}
                    {data.meta.unrankable_tickers.join(", ")}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
