/**
 * 엔트리 — RouterProvider 마운트. SW 등록은 vite-plugin-pwa(registerType:autoUpdate)가 자동.
 *
 * react-router 7: RouterProvider 는 `react-router/dom` 에서(DOM 전용 진입점).
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import { router } from "./router";
import "./styles.css";

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("#root 엘리먼트를 찾을 수 없습니다");

createRoot(rootEl).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
