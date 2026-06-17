/**
 * 백테스트 — placeholder(다음 마일스톤). 라우트 골격만, 본문은 백테스트 엔진 구현 시 채운다.
 *
 * §4.1 명시: 현재 랭킹은 백테스트로 검증되지 않았으므로 "알파"가 아니다. 이 페이지가 채워져야
 * (수익률 곡선·드로다운·생존편향/룩어헤드 가드 결과) 비로소 룰을 신뢰할 근거가 생긴다.
 */

import { Link } from "react-router";
import { Badge } from "../components/common/Badge";

export function BacktestPage() {
  return (
    <div>
      <header className="page-head">
        <h1>백테스트</h1>
        <p>룰 검증 — 수익률 곡선·드로다운·편향 가드 결과를 보여줄 화면입니다.</p>
      </header>

      <div className="card">
        <div className="placeholder-box">
          <div className="big">🧪</div>
          <h2 style={{ marginTop: 0 }}>준비 중 — 다음 마일스톤</h2>
          <p>
            <Badge tone="warn">랭킹 미검증 (§4.1)</Badge>
          </p>
          <p style={{ maxWidth: 480, margin: "0.75rem auto 0" }}>
            현재 랭킹은 백테스트로 검증되지 않아 <strong>알파(초과수익)가 아닙니다</strong>. 백테스트
            엔진이 완성되면 이 화면에서 룰을 직접 실행·검증하고, 생존편향·룩어헤드 가드 통과 결과를
            확인할 수 있습니다.
          </p>
          <p style={{ marginTop: "1rem" }}>
            <Link to="/">랭킹 대시보드로 →</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
