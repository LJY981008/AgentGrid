/**
 * 추적 화면(M4) — 월 라운드 운용 기록·4계열 성과 비교·구조화 회고.
 *
 * 흐름: 라운드 생성(Top20 스냅샷 자동 캡처) → Claude 토의 후 Top5 확정 → 입금 → 매수 기록
 * → 성과 확인(실보유/Top5모델/Top20등가중/SPY + 선택·실행효과) → 월말 마감(성과 프리뷰 →
 * 구조화 회고 → 동결).
 *
 * ⭐ §4.1: UnvalidatedWarning 상시(라운드 생성 시점 validated 동결 값 기준·fail-safe).
 * 원칙: 계산은 전부 서버(return_convention="price" — 배당 미반영 명시). 프론트는 표시·입력만.
 * 폼 검증은 UX 보조 — 진짜 가드는 서버(422/409 메시지 그대로 노출).
 */

import { useState } from "react";
import {
  getPerformance,
  getRound,
  getRounds,
  patchTop5,
  postBenchmarkSync,
  postCashFlow,
  postCloseRound,
  postRound,
  postTrade,
  postVoidTrade,
} from "../api/endpoints";
import { ApiError } from "../api/client";
import { useApi } from "../api/useApi";
import type { Performance, Retrospective, Round, SeriesPerf, TradeCreate } from "../api/types";
import { UnvalidatedWarning } from "../components/common/UnvalidatedWarning";
import { ErrorView, Loading } from "../components/common/StateViews";

function errMsg(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return String(e);
}

const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export function TrackingPage() {
  const rounds = useApi((signal) => getRounds(signal), []);
  const openItem = rounds.data?.find((r) => r.status === "open") ?? null;
  const active = useApi(
    (signal) => (openItem ? getRound(openItem.id, signal) : Promise.resolve(null)),
    [openItem?.id],
  );

  return (
    <section>
      <h1>추적 — 월 라운드 운용 기록</h1>
      <UnvalidatedWarning validated={active.data?.validated} warning={active.data?.warning} />
      {rounds.loading && <Loading label="라운드 목록" />}
      {rounds.error && <ErrorView error={rounds.error} onRetry={rounds.refetch} />}
      {rounds.data && !openItem && <NewRoundCard onCreated={rounds.refetch} />}
      {openItem && active.loading && <Loading label="활성 라운드" />}
      {openItem && active.error && <ErrorView error={active.error} onRetry={active.refetch} />}
      {active.data && (
        <ActiveRound
          round={active.data}
          onChanged={() => {
            active.refetch();
            rounds.refetch();
          }}
        />
      )}
      {rounds.data && rounds.data.some((r) => r.status === "closed") && (
        <PastRounds ids={rounds.data.filter((r) => r.status === "closed").map((r) => r.id)} />
      )}
    </section>
  );
}

// ── 라운드 생성 ──────────────────────────────────────────────────────────────

function NewRoundCard({ onCreated }: { onCreated: () => void }) {
  const now = new Date();
  const defaultLabel = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const [label, setLabel] = useState(defaultLabel);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      await postRound(label.trim());
      onCreated();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h2>새 라운드 시작</h2>
      <p className="notice">
        생성 시점의 정량 Top20 랭킹이 스냅샷으로 동결됩니다(재현성). 이후 Claude 토의로 Top5 를
        확정하고, 입금 → 매수 기록 순서로 진행하세요.
      </p>
      <div className="form-row">
        <label htmlFor="round-label">라벨</label>
        <input
          id="round-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="2026-07"
        />
        <button className="btn" disabled={busy || !label.trim()} onClick={create}>
          {busy ? "생성 중…" : "라운드 시작"}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}

// ── 활성 라운드 ──────────────────────────────────────────────────────────────

function ActiveRound({ round, onChanged }: { round: Round; onChanged: () => void }) {
  return (
    <>
      <div className="card">
        <h2>
          {round.label} <span className="badge neutral">진행중</span>
        </h2>
        <div className="kv-grid">
          <div className="kv">
            <span>스냅샷 기준일</span>
            <strong>{round.anchor_as_of}</strong>
          </div>
          <div className="kv">
            <span>시작일</span>
            <strong>{round.opened_on}</strong>
          </div>
          <div className="kv">
            <span>Top5</span>
            <strong>{round.top5.length ? round.top5.join(" · ") : "미확정"}</strong>
          </div>
        </div>
      </div>
      {!round.top5.length && <Top5Form round={round} onChanged={onChanged} />}
      <Snapshot round={round} />
      <CashFlowForm round={round} onChanged={onChanged} />
      <TradeForm round={round} onChanged={onChanged} />
      <TradeList round={round} onChanged={onChanged} />
      <PerformanceCard round={round} />
      {round.top5.length > 0 && <CloseFlow round={round} onChanged={onChanged} />}
    </>
  );
}

function Snapshot({ round }: { round: Round }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card">
      <h3>
        Top20 스냅샷(동결){" "}
        <button className="btn secondary" onClick={() => setOpen(!open)}>
          {open ? "접기" : "펼치기"}
        </button>
      </h3>
      {open && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>티커</th>
                <th>점수</th>
                <th>앵커 종가</th>
              </tr>
            </thead>
            <tbody>
              {round.top20.map((e) => (
                <tr key={e.ticker}>
                  <td>{e.rank}</td>
                  <td>{e.ticker}</td>
                  <td>{e.score.toFixed(4)}</td>
                  <td>{e.anchor_close === null ? "—" : usd(e.anchor_close)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Top5Form({ round, onChanged }: { round: Round; onChanged: () => void }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [memo, setMemo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (t: string) =>
    setPicked((p) => (p.includes(t) ? p.filter((x) => x !== t) : p.length < 5 ? [...p, t] : p));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await patchTop5(round.id, memo.trim(), picked);
      onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h3>Top5 확정 (Claude 토의 후)</h3>
      <p className="notice">Top20 중 최대 5종목. 확정 전에는 매수 입력이 잠깁니다(규율 순서).</p>
      <div className="pick-grid">
        {round.top20.map((e) => (
          <button
            key={e.ticker}
            className={`btn ${picked.includes(e.ticker) ? "" : "secondary"}`}
            onClick={() => toggle(e.ticker)}
          >
            {e.ticker}
          </button>
        ))}
      </div>
      <div className="form-col">
        <label htmlFor="top5-memo">토의 요약(선정 근거)</label>
        <textarea
          id="top5-memo"
          rows={3}
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
          placeholder="Claude 세션 토의 요약 — 왜 이 5종목인가"
        />
      </div>
      <button
        className="btn"
        disabled={busy || picked.length === 0 || memo.trim().length < 5}
        onClick={submit}
      >
        {busy ? "저장 중…" : `Top5 확정 (${picked.length}/5)`}
      </button>
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}

function CashFlowForm({ round, onChanged }: { round: Round; onChanged: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  const [amount, setAmount] = useState("");
  const [flowedOn, setFlowedOn] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await postCashFlow(round.id, { amount, flowed_on: flowedOn });
      setAmount("");
      onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <h3>입출금 기록</h3>
      <p className="notice">매수 전 입금 필수(현금 원장). 입금 +, 출금 − (USD).</p>
      <div className="form-row">
        <input
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="예: 1000 (출금은 -500)"
          aria-label="금액(USD)"
        />
        <input
          type="date"
          value={flowedOn}
          onChange={(e) => setFlowedOn(e.target.value)}
          aria-label="일자"
        />
        <button className="btn" disabled={busy || !amount.trim()} onClick={submit}>
          기록
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}

function TradeForm({ round, onChanged }: { round: Round; onChanged: () => void }) {
  const today = new Date().toISOString().slice(0, 10);
  // 티커 선택형(자유 입력 금지) — Top5 ∪ 이월 포지션 ∪ 이번 라운드 거래 종목.
  const options = Array.from(
    new Set([
      ...round.top5,
      ...round.carry_in.map((c) => c.ticker),
      ...round.trades.filter((t) => !t.voided_at).map((t) => t.ticker),
    ]),
  ).sort();
  const [form, setForm] = useState<TradeCreate>({
    ticker: "",
    side: "BUY",
    quantity: "",
    price: "",
    fee: "0",
    executed_on: today,
  });
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready =
    form.ticker && Number(form.quantity) > 0 && Number(form.price) > 0 && form.executed_on;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await postTrade(round.id, form);
      setForm({ ...form, quantity: "", price: "" });
      setConfirming(false);
      onChanged();
    } catch (e) {
      setError(errMsg(e));
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  };

  if (!round.top5.length) return null; // Top5 확정 전 매수 잠금(서버 422 와 동일 규율)

  return (
    <div className="card">
      <h3>체결 기록</h3>
      <div className="form-col">
        <div className="form-row">
          <select
            value={form.ticker}
            onChange={(e) => setForm({ ...form, ticker: e.target.value })}
            aria-label="종목"
          >
            <option value="">종목 선택</option>
            {options.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select
            value={form.side}
            onChange={(e) => setForm({ ...form, side: e.target.value as "BUY" | "SELL" })}
            aria-label="방향"
          >
            <option value="BUY">매수</option>
            <option value="SELL">매도</option>
          </select>
        </div>
        <div className="form-row">
          <input
            inputMode="decimal"
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            placeholder="수량"
            aria-label="수량"
          />
          <input
            inputMode="decimal"
            value={form.price}
            onChange={(e) => setForm({ ...form, price: e.target.value })}
            placeholder="체결 단가(USD)"
            aria-label="체결 단가"
          />
        </div>
        <div className="form-row">
          <input
            inputMode="decimal"
            value={form.fee ?? "0"}
            onChange={(e) => setForm({ ...form, fee: e.target.value })}
            placeholder="수수료(USD)"
            aria-label="수수료"
          />
          <input
            type="date"
            value={form.executed_on}
            onChange={(e) => setForm({ ...form, executed_on: e.target.value })}
            aria-label="체결일"
          />
        </div>
        {!confirming ? (
          <button className="btn" disabled={!ready || busy} onClick={() => setConfirming(true)}>
            입력 확인
          </button>
        ) : (
          <div className="confirm-box">
            <p>
              <strong>
                {form.ticker} {form.side === "BUY" ? "매수" : "매도"} {form.quantity}주 @{" "}
                {form.price} USD (수수료 {form.fee || "0"})
              </strong>{" "}
              — {form.executed_on}
            </p>
            <div className="form-row">
              <button className="btn" disabled={busy} onClick={submit}>
                {busy ? "기록 중…" : "확정 기록"}
              </button>
              <button className="btn secondary" onClick={() => setConfirming(false)}>
                취소
              </button>
            </div>
          </div>
        )}
        {error && <p className="form-error">{error}</p>}
      </div>
    </div>
  );
}

function TradeList({ round, onChanged }: { round: Round; onChanged: () => void }) {
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!round.trades.length && !round.cash_flows.length) return null;

  const voidTrade = async (id: number) => {
    const reason = window.prompt("void 사유(오입력 정정 — 감사 기록):");
    if (!reason || reason.trim().length < 2) return;
    setBusyId(id);
    setError(null);
    try {
      await postVoidTrade(id, reason.trim());
      onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="card">
      <h3>거래·입출금 이력</h3>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>일자</th>
              <th>내용</th>
              <th>금액</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {round.cash_flows.map((f) => (
              <tr key={`f${f.id}`} className={f.voided_at ? "voided" : ""}>
                <td>{f.flowed_on}</td>
                <td>{f.amount >= 0 ? "입금" : "출금"}</td>
                <td>{usd(f.amount)}</td>
                <td />
              </tr>
            ))}
            {round.trades.map((t) => (
              <tr key={`t${t.id}`} className={t.voided_at ? "voided" : ""}>
                <td>{t.executed_on}</td>
                <td>
                  {t.ticker} {t.side === "BUY" ? "매수" : "매도"} {t.quantity}주 @ {t.price}
                  {t.voided_at && <span className="badge danger">void</span>}
                </td>
                <td>{usd(t.quantity * t.price * (t.side === "BUY" ? -1 : 1) - t.fee)}</td>
                <td>
                  {!t.voided_at && round.status === "open" && (
                    <button
                      className="btn secondary"
                      disabled={busyId === t.id}
                      onClick={() => voidTrade(t.id)}
                    >
                      정정
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}

// ── 성과 ────────────────────────────────────────────────────────────────────

function SeriesRow({ label, s }: { label: string; s: SeriesPerf }) {
  return (
    <tr>
      <td>{label}</td>
      <td className={s.cumulative_return >= 0 ? "pos" : "neg"}>{pct(s.cumulative_return)}</td>
      <td>{pct(-s.max_drawdown)}</td>
      <td>{s.unmeasurable.length ? `측정불가: ${s.unmeasurable.join(",")}` : ""}</td>
    </tr>
  );
}

function PerformanceView({ perf }: { perf: Performance }) {
  return (
    <>
      <p className="notice">
        가격 기준일 <strong>{perf.as_of}</strong>
        {perf.stale && <span className="badge warn">stale — 수집 필요</span>} · 전 계열{" "}
        <strong>배당 미반영(price return)</strong>·USD 기준
        {perf.verdict_deferred && (
          <>
            {" "}
            · <span className="badge warn">판정 유보(누적 {perf.n_picks_cumulative}/20 pick)</span>
          </>
        )}
      </p>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>계열</th>
              <th>누적수익</th>
              <th>MDD</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <SeriesRow label="① 실보유" s={perf.actual} />
            <SeriesRow label="② Top5 모델" s={perf.top5_model} />
            <SeriesRow label="③ Top20 등가중" s={perf.top20_model} />
            <SeriesRow label="④ SPY" s={perf.spy} />
          </tbody>
        </table>
      </div>
      <div className="kv-grid">
        <div className="kv">
          <span>선택효과(②−③) — 수동 압축의 가치</span>
          <strong className={perf.selection_effect >= 0 ? "pos" : "neg"}>
            {pct(perf.selection_effect)}
          </strong>
        </div>
        <div className="kv">
          <span>실행효과(①−②) — 체결·현금드래그</span>
          <strong className={perf.execution_effect >= 0 ? "pos" : "neg"}>
            {pct(perf.execution_effect)}
          </strong>
        </div>
        <div className="kv">
          <span>히트레이트(Top5 중 수익 종목)</span>
          <strong>{perf.hit_rate === null ? "—" : pct(perf.hit_rate)}</strong>
        </div>
      </div>
      {perf.contributions.length > 0 && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>종목 기여도</th>
                <th>P&L</th>
              </tr>
            </thead>
            <tbody>
              {perf.contributions.map((c) => (
                <tr key={c.ticker}>
                  <td>{c.ticker}</td>
                  <td className={c.pnl >= 0 ? "pos" : "neg"}>{usd(c.pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {perf.liquidated.length > 0 && (
        <p className="notice">폐지 청산(마지막 유효가 동결): {perf.liquidated.join(", ")}</p>
      )}
    </>
  );
}

function PerformanceCard({ round }: { round: Round }) {
  const [perf, setPerf] = useState<Performance | null>(null);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setBusy(true);
    setError(null);
    try {
      setPerf(await getPerformance(round.id));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const sync = async () => {
    setSyncing(true);
    setError(null);
    try {
      await postBenchmarkSync();
      await load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="card">
      <h3>성과 (4계열 비교)</h3>
      <div className="form-row">
        <button className="btn" disabled={busy} onClick={load}>
          {busy ? "계산 중…" : "성과 조회"}
        </button>
        <button className="btn secondary" disabled={syncing} onClick={sync}>
          {syncing ? "동기화 중…" : "벤치(SPY)·분할 동기화"}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      {perf && <PerformanceView perf={perf} />}
    </div>
  );
}

// ── 마감(2단계: 성과 프리뷰 → 구조화 회고) ──────────────────────────────────

function CloseFlow({ round, onChanged }: { round: Round; onChanged: () => void }) {
  const [preview, setPreview] = useState<Performance | null>(null);
  const [retro, setRetro] = useState<Retrospective>({
    judgment_good: "",
    judgment_bad: "",
    rule_change: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openPreview = async () => {
    setBusy(true);
    setError(null);
    try {
      setPreview(await getPerformance(round.id));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await postCloseRound(round.id, retro);
      onChanged();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const ready =
    retro.judgment_good.trim().length >= 5 &&
    retro.judgment_bad.trim().length >= 5 &&
    retro.rule_change.trim().length >= 2;

  return (
    <div className="card">
      <h3>라운드 마감</h3>
      {!preview ? (
        <>
          <p className="notice">
            마감 = 성과 동결 + 구조화 회고(필수). 성과 프리뷰를 먼저 확인한 뒤 회고를 작성합니다.
            가격 기준일이 오래되면(stale) 마감이 거부됩니다 — 데이터 수집 먼저.
          </p>
          <button className="btn" disabled={busy} onClick={openPreview}>
            {busy ? "불러오는 중…" : "마감 시작(성과 프리뷰)"}
          </button>
        </>
      ) : (
        <>
          <PerformanceView perf={preview} />
          {preview.stale ? (
            <p className="form-error">가격 기준일 stale — 데이터 화면에서 수집 후 다시 시도.</p>
          ) : (
            <div className="form-col">
              <p className="notice">
                회고는 결과(이겼다/졌다)가 아니라 <strong>과정(판단 근거)</strong>을 채점하세요 —
                한 달 수익은 노이즈입니다(판정 유보 라벨 참조).
              </p>
              <label htmlFor="retro-good">잘한 판단(근거)</label>
              <textarea
                id="retro-good"
                rows={2}
                value={retro.judgment_good}
                onChange={(e) => setRetro({ ...retro, judgment_good: e.target.value })}
              />
              <label htmlFor="retro-bad">잘못한 판단(근거)</label>
              <textarea
                id="retro-bad"
                rows={2}
                value={retro.judgment_bad}
                onChange={(e) => setRetro({ ...retro, judgment_bad: e.target.value })}
              />
              <label htmlFor="retro-rule">다음 라운드 규칙 변경(없으면 "없음")</label>
              <textarea
                id="retro-rule"
                rows={2}
                value={retro.rule_change}
                onChange={(e) => setRetro({ ...retro, rule_change: e.target.value })}
              />
              <button className="btn" disabled={!ready || busy} onClick={submit}>
                {busy ? "마감 중…" : "회고 저장 + 라운드 마감(동결)"}
              </button>
            </div>
          )}
          {error && <p className="form-error">{error}</p>}
        </>
      )}
    </div>
  );
}

// ── 지난 라운드 ──────────────────────────────────────────────────────────────

function PastRounds({ ids }: { ids: number[] }) {
  const [openId, setOpenId] = useState<number | null>(null);
  const detail = useApi(
    (signal) => (openId ? getRound(openId, signal) : Promise.resolve(null)),
    [openId],
  );

  return (
    <div className="card">
      <h3>지난 라운드</h3>
      <div className="form-row">
        {ids.map((id) => (
          <button
            key={id}
            className={`btn ${openId === id ? "" : "secondary"}`}
            onClick={() => setOpenId(openId === id ? null : id)}
          >
            #{id}
          </button>
        ))}
      </div>
      {detail.loading && <Loading label="라운드 상세" />}
      {detail.data && (
        <div>
          <h4>
            {detail.data.label}{" "}
            <span className="badge neutral">{detail.data.closed_at?.slice(0, 10)} 마감</span>
          </h4>
          <UnvalidatedWarning validated={detail.data.validated} warning={detail.data.warning} />
          <p>Top5: {detail.data.top5.join(" · ")}</p>
          {detail.data.retrospective && (
            <div className="kv-grid">
              <div className="kv">
                <span>잘한 판단</span>
                <strong>{detail.data.retrospective.judgment_good}</strong>
              </div>
              <div className="kv">
                <span>잘못한 판단</span>
                <strong>{detail.data.retrospective.judgment_bad}</strong>
              </div>
              <div className="kv">
                <span>규칙 변경</span>
                <strong>{detail.data.retrospective.rule_change}</strong>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
