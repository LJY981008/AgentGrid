import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <div className="placeholder-box">
      <div className="big">🧭</div>
      <h1>페이지를 찾을 수 없습니다</h1>
      <p>
        <Link to="/">랭킹 대시보드로 돌아가기</Link>
      </p>
    </div>
  );
}
