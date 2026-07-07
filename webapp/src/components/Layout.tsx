/**
 * 앱 셸 — 하단 탭바(모바일) / 좌측 사이드바(데스크탑) + 콘텐츠 아웃렛.
 *
 * 모바일 우선: 기본은 하단 고정 탭바, 768px 이상에서 좌측 사이드바로 전환(styles.css 미디어쿼리).
 * react-router 7 의 <Outlet/> 에 각 페이지가 렌더된다.
 */

import { NavLink, Outlet } from "react-router";

interface Tab {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

const TABS: Tab[] = [
  { to: "/", label: "랭킹", icon: "📊", end: true },
  { to: "/tracking", label: "추적", icon: "💼" },
  { to: "/data", label: "데이터", icon: "🗄️" },
  { to: "/universe", label: "종목", icon: "📜" },
  { to: "/learn", label: "학습", icon: "📚" },
  { to: "/backtest", label: "백테스트", icon: "🧪" },
];

export function Layout() {
  return (
    <div className="app-shell">
      <nav className="tabbar" aria-label="주요 메뉴">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            <span className="tab-ico" aria-hidden>
              {t.icon}
            </span>
            <span>{t.label}</span>
          </NavLink>
        ))}
      </nav>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
