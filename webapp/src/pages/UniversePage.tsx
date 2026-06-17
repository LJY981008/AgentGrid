/**
 * 종목(유니버스) — 적재된 종목 목록 읽기 전용.
 *
 * dataset 요약의 tickers[] 를 표로 보여준다(읽기 위주 — 편집·정렬 로직 없음). 종목별 행수·기간·
 * 소스를 한눈에. 거래소별로 묶어 가독성↑(표시용 그룹핑일 뿐).
 */

import { Link } from "react-router";
import { getDataset } from "../api/endpoints";
import { useApi } from "../api/useApi";
import type { DatasetTicker } from "../api/types";
import { ErrorView, Loading } from "../components/common/StateViews";
import { fmtDate, fmtInt } from "../lib/format";

function groupByExchange(tickers: DatasetTicker[]): [string, DatasetTicker[]][] {
  const map = new Map<string, DatasetTicker[]>();
  for (const t of tickers) {
    const arr = map.get(t.exchange) ?? [];
    arr.push(t);
    map.set(t.exchange, arr);
  }
  for (const arr of map.values()) arr.sort((a, b) => a.ticker.localeCompare(b.ticker));
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

export function UniversePage() {
  const { data, loading, error, refetch } = useApi((signal) => getDataset(signal), []);

  return (
    <div>
      <header className="page-head">
        <h1>적재 종목</h1>
        <p>현재 데이터셋에 들어있는 종목 목록입니다.</p>
      </header>

      <div className="card">
        {loading && <Loading />}
        {error && <ErrorView error={error} onRetry={refetch} />}
        {data && !loading && !error && (
          <>
            {data.tickers.length === 0 ? (
              <div className="state-box">
                <p style={{ marginTop: 0 }}>적재된 종목이 없습니다.</p>
                <p>
                  <Link to="/data">데이터 페이지</Link>에서 수집하세요.
                </p>
              </div>
            ) : (
              groupByExchange(data.tickers).map(([exchange, group]) => (
                <section key={exchange} style={{ marginBottom: "1.25rem" }}>
                  <div className="group-head">
                    <span>{exchange}</span>
                    <span>· {group.length}종목</span>
                  </div>
                  <div className="table-wrap">
                    <table className="data">
                      <thead>
                        <tr>
                          <th>종목</th>
                          <th className="num">행수</th>
                          <th>시작</th>
                          <th>종료</th>
                          <th>소스</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.map((t) => (
                          <tr key={t.ticker}>
                            <td>{t.ticker}</td>
                            <td className="num">{fmtInt(t.row_count)}</td>
                            <td>{fmtDate(t.min_date)}</td>
                            <td>{fmtDate(t.max_date)}</td>
                            <td>{t.source ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              ))
            )}
          </>
        )}
      </div>
    </div>
  );
}
