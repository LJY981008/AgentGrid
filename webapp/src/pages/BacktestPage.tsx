/**
 * 백테스트 — 룰 골격 자산곡선·지표·벤치 대비.
 *
 * §4.1 BLOCKING: 산출 지표는 골격·미검증 → UnvalidatedWarning 상시 + data_caveats 노출. 알파 아님.
 * 투자 로직(백테스트 계산)은 전부 서버(/api/backtest) — 프론트는 표시·컨트롤만(group 토글처럼 전략·
 * 리밸주기 변경 시 서버 재계산 요청, 프론트는 곡선/지표를 그리기만). 차트=Recharts(webapp-conventions).
 */

import { useState } from "react";
import { Link } from "react-router";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getBacktest } from "../api/endpoints";
import type { BacktestQuery } from "../api/types";
import { useApi } from "../api/useApi";
import { Badge } from "../components/common/Badge";
import { ErrorView, Loading } from "../components/common/StateViews";
import { UnvalidatedWarning } from "../components/common/UnvalidatedWarning";
import { fmtNum, fmtPct } from "../lib/format";

const _BENCH_KEY = "EQUAL_WEIGHT_UNIVERSE";

export function BacktestPage() {
  const [strategy, setStrategy] = useState<"equal_weight" | "score_weight">("equal_weight");
  const [rebalance, setRebalance] = useState<"monthly" | "quarterly">("monthly");
  const query: BacktestQuery = { strategy, rebalance_freq: rebalance, top_n: 5 };
  const { data, loading, error, refetch } = useApi(
    (signal) => getBacktest(query, signal),
    [strategy, rebalance],
  );

  return (
    <div>
      <header className="page-head">
        <h1>백테스트</h1>
        <p>룰을 과거 시점마다 굴려 검증 — 자산곡선·위험조정 지표·벤치 대비.</p>
      </header>

      {/* 경고는 데이터·로딩·에러와 무관하게 항상 먼저(누락 시에도 노출). */}
      <UnvalidatedWarning validated={data?.meta.validated} warning={data?.meta.warning} />

      <div className="card">
        <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
          <button
            className={strategy === "equal_weight" ? "btn" : "btn secondary"}
            onClick={() => setStrategy("equal_weight")}
          >
            동일가중
          </button>
          <button
            className={strategy === "score_weight" ? "btn" : "btn secondary"}
            onClick={() => setStrategy("score_weight")}
          >
            점수가중
          </button>
          <span style={{ width: "0.5rem" }} />
          <button
            className={rebalance === "monthly" ? "btn" : "btn secondary"}
            onClick={() => setRebalance("monthly")}
          >
            월간 리밸
          </button>
          <button
            className={rebalance === "quarterly" ? "btn" : "btn secondary"}
            onClick={() => setRebalance("quarterly")}
          >
            분기 리밸
          </button>
        </div>

        {loading && <Loading label="백테스트 실행 중…" />}
        {error && <ErrorView error={error} onRetry={refetch} />}

        {data && !loading && !error && (
          <>
            {data.equity_curve.length === 0 ? (
              <div className="state-box">
                <p style={{ marginTop: 0 }}>아직 적재된 데이터가 없어 백테스트를 돌릴 수 없습니다.</p>
                <p>
                  먼저 <Link to="/data">데이터 페이지</Link>에서 종목을 수집하세요.
                </p>
              </div>
            ) : (
              <>
                <BacktestChart data={data} />
                <MetricsGrid data={data} />
                <CaveatList caveats={data.meta.data_caveats} />
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function BacktestChart({ data }: { data: import("../api/types").BacktestResponse }) {
  // 전략·벤치 곡선을 날짜 기준 zip(둘 다 같은 리밸 날짜·앵커라 인덱스 정렬 일치).
  const merged = data.equity_curve.map((p, i) => ({
    date: p.date,
    strategy: p.value,
    benchmark: data.benchmark_curve[i]?.value ?? null,
  }));
  return (
    <div style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <LineChart data={merged} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={32} />
          <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} width={48} />
          <Tooltip formatter={(v: unknown) => fmtNum(typeof v === "number" ? v : null, 3)} />
          <Legend />
          <Line type="monotone" dataKey="strategy" name="전략" stroke="#4ea1ff" dot={false} />
          <Line type="monotone" dataKey="benchmark" name="등가중 벤치" stroke="#999" strokeDasharray="4 3" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function MetricsGrid({ data }: { data: import("../api/types").BacktestResponse }) {
  const m = data.metrics;
  const bench = data.benchmark_returns[_BENCH_KEY];
  const excess = bench === undefined ? null : m.total_return - bench;
  const cells: Array<[string, string]> = [
    ["총수익", fmtPct(m.total_return)],
    ["CAGR", fmtPct(m.cagr)],
    ["Sharpe", fmtNum(m.sharpe, 2)],
    ["Sortino", fmtNum(m.sortino, 2)],
    ["MDD", fmtPct(m.max_drawdown)],
    ["회전율", fmtNum(m.turnover, 2)],
    ["리밸 기간", String(m.n_rebalances)],
    ["폐지청산", String(m.n_delisted_liquidations)],
    [`벤치(${_BENCH_KEY === "EQUAL_WEIGHT_UNIVERSE" ? "등가중" : _BENCH_KEY})`, fmtPct(bench)],
    ["초과수익", excess === null ? "—" : fmtPct(excess)],
  ];
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
        gap: "0.5rem",
        marginTop: "0.75rem",
      }}
    >
      {cells.map(([label, value]) => (
        <div key={label} className="state-box" style={{ padding: "0.6rem" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>{label}</div>
          <div style={{ fontSize: "1.05rem", fontWeight: 600 }}>{value}</div>
        </div>
      ))}
    </div>
  );
}

function CaveatList({ caveats }: { caveats: string[] }) {
  if (caveats.length === 0) return null;
  return (
    <div className="notice" style={{ marginTop: "0.75rem" }}>
      <p style={{ margin: "0 0 0.25rem" }}>
        <Badge tone="warn">미검증 한계</Badge>
      </p>
      <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
        {caveats.map((c) => (
          <li key={c} style={{ fontSize: "0.85rem" }}>
            {c}
          </li>
        ))}
      </ul>
    </div>
  );
}
