/**
 * 데이터 — 적재 현황 요약 + 라이브 수집(ingest) 트리거 + 결과표.
 *
 * ⚠️ ingest 는 라이브 EODHD **무료 티어(20콜/일)** 를 실제로 소비한다(데모=9콜). 버튼에 고지하고
 * 429(한도 초과) 응답은 친화 메시지로 분기한다. 수집 성공 후 dataset 요약을 자동 재조회한다
 * (첫 실행 흐름: 빈 데이터셋 → 수집 → 요약·랭킹 채워짐).
 *
 * 수집은 "트리거"일 뿐 — 어떤 종목을 어떻게 수집할지(데모 유니버스·콜수)는 전부 서버가 결정한다.
 */

import { useState } from "react";
import { Link } from "react-router";
import { getDataset, postIngest } from "../api/endpoints";
import { useApi } from "../api/useApi";
import { ApiError } from "../api/client";
import type { IngestResult } from "../api/types";
import { Badge } from "../components/common/Badge";
import { ErrorView, Loading } from "../components/common/StateViews";
import { fmtDate, fmtInt } from "../lib/format";

function IngestResultTable({ result }: { result: IngestResult }) {
  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
        <h2 style={{ margin: 0 }}>수집 결과</h2>
        {result.passed ? (
          <Badge tone="ok">검증 통과</Badge>
        ) : (
          <Badge tone="danger">검증 실패</Badge>
        )}
      </div>
      <div className="kv-grid" style={{ marginBottom: "0.75rem" }}>
        <div className="kv">
          <div className="k">적재 종목</div>
          <div className="v">{fmtInt(result.ingested_ticker_count)}</div>
        </div>
        <div className="kv">
          <div className="k">총 행수</div>
          <div className="v">{fmtInt(result.total_rows)}</div>
        </div>
        <div className="kv">
          <div className="k">빈 종목</div>
          <div className="v">{fmtInt(result.empty_tickers.length)}</div>
        </div>
        <div className="kv">
          <div className="k">실패 종목</div>
          <div className="v">{fmtInt(result.failed_tickers.length)}</div>
        </div>
      </div>

      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>종목</th>
              <th>거래소</th>
              <th className="num">행수</th>
              <th>시작</th>
              <th>종료</th>
              <th>비고</th>
            </tr>
          </thead>
          <tbody>
            {result.results.map((r) => (
              <tr key={`${r.exchange}-${r.ticker}`}>
                <td>{r.ticker}</td>
                <td>{r.exchange}</td>
                <td className="num">{fmtInt(r.bar_count)}</td>
                <td>{fmtDate(r.min_date)}</td>
                <td>{fmtDate(r.max_date)}</td>
                <td>
                  {r.error
                    ? r.error
                    : r.bar_count === 0
                      ? "데이터 부족(소스 빈 결과)"
                      : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {result.verification && !result.verification.passed && (
        <div className="notice" style={{ marginTop: "0.75rem", color: "var(--danger)" }}>
          무결성 경고: 중복 {result.verification.duplicate_count} · OHLC 위반{" "}
          {result.verification.ohlc_violation_count} · 누락 종목{" "}
          {result.verification.missing_tickers.length} · 부분 소실{" "}
          {result.verification.shortfall_tickers.length}
        </div>
      )}
    </div>
  );
}

export function DataPage() {
  const dataset = useApi((signal) => getDataset(signal), []);

  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<IngestResult | null>(null);
  const [ingestError, setIngestError] = useState<ApiError | null>(null);

  async function runIngest() {
    if (ingesting) return;
    setIngesting(true);
    setIngestError(null);
    try {
      // tickers 생략 → 서버 데모 9종목(무료 9콜). 종목 지정 UI 는 후속(현재는 데모 트리거만).
      const res = await postIngest({});
      setIngestResult(res);
      dataset.refetch(); // 수집 후 요약 갱신
    } catch (err) {
      setIngestError(err instanceof ApiError ? err : new ApiError("알 수 없는 오류", 0));
    } finally {
      setIngesting(false);
    }
  }

  const ds = dataset.data;

  return (
    <div>
      <header className="page-head">
        <h1>데이터</h1>
        <p>적재 현황을 확인하고, 라이브 수집을 실행합니다.</p>
      </header>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>적재 현황</h2>
        {dataset.loading && <Loading />}
        {dataset.error && <ErrorView error={dataset.error} onRetry={dataset.refetch} />}
        {ds && !dataset.loading && !dataset.error && (
          <>
            {ds.ticker_count === 0 ? (
              <div className="state-box">아직 적재된 데이터가 없습니다. 아래에서 수집하세요.</div>
            ) : (
              <>
                <div className="kv-grid">
                  <div className="kv">
                    <div className="k">종목 수</div>
                    <div className="v">{fmtInt(ds.ticker_count)}</div>
                  </div>
                  <div className="kv">
                    <div className="k">총 행수</div>
                    <div className="v">{fmtInt(ds.total_rows)}</div>
                  </div>
                  <div className="kv">
                    <div className="k">기간 시작</div>
                    <div className="v">{fmtDate(ds.min_date)}</div>
                  </div>
                  <div className="kv">
                    <div className="k">기간 종료</div>
                    <div className="v">{fmtDate(ds.max_date)}</div>
                  </div>
                </div>
                {ds.sources.length > 0 && (
                  <div className="rank-meta" style={{ marginTop: "0.5rem" }}>
                    소스: {ds.sources.join(", ")}
                  </div>
                )}
                <p style={{ marginBottom: 0 }}>
                  <Link to="/universe">적재 종목 전체 보기 →</Link>
                </p>
              </>
            )}
          </>
        )}
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>라이브 수집</h2>
        <div className="notice">
          ⚠ 데모 수집은 EODHD <strong>무료 티어(하루 20콜)</strong> 중 9콜을 실제로 사용합니다.
          하루 한도를 넘기면 다음 날 리셋까지 수집할 수 없습니다.
        </div>
        <button className="btn" onClick={runIngest} disabled={ingesting}>
          {ingesting ? "수집 중… (수초 소요)" : "데모 9종목 수집"}
        </button>

        {ingestError && (
          <div style={{ marginTop: "0.75rem" }}>
            <ErrorView error={ingestError} onRetry={runIngest} />
          </div>
        )}
      </div>

      {ingestResult && <IngestResultTable result={ingestResult} />}
    </div>
  );
}
