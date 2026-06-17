/**
 * 라우트 정의 — react-router 7 Data Mode(createBrowserRouter + RouterProvider).
 *
 * ⚠️ react-router-dom 은 폐기 — 전부 `react-router` 에서 import(DOM 전용은 `react-router/dom`).
 * 5개 화면: 랭킹(홈)·데이터·종목·학습·백테스트(placeholder).
 */

import { createBrowserRouter } from "react-router";
import { Layout } from "./components/Layout";
import { DashboardPage } from "./pages/DashboardPage";
import { DataPage } from "./pages/DataPage";
import { UniversePage } from "./pages/UniversePage";
import { LearningPage } from "./pages/LearningPage";
import { BacktestPage } from "./pages/BacktestPage";
import { NotFoundPage } from "./pages/NotFoundPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "data", element: <DataPage /> },
      { path: "universe", element: <UniversePage /> },
      { path: "learn", element: <LearningPage /> },
      { path: "backtest", element: <BacktestPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
