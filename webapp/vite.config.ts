import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// dev 프록시 대상(API 서버). compose 에서 web 서비스가 app(uvicorn) 을 가리킬 때도
// 동일하게 same-origin(/api) 으로 호출 → CORS 회피. 운영 베이스는 VITE_API_BASE 로 분리.
const API_TARGET = process.env.VITE_DEV_API_TARGET ?? "http://localhost:8000";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "icons/apple-touch-icon.png"],
      manifest: {
        name: "stockpick — 개인 투자 대시보드",
        short_name: "stockpick",
        description:
          "개인 1인용 미국 주식 분석 대시보드 (랭킹·데이터·학습). 백테스트 검증 전 룰은 알파 아님.",
        theme_color: "#0f172a",
        background_color: "#0f172a",
        display: "standalone",
        start_url: "/",
        scope: "/",
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "icons/icon-512-maskable.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // 앱셸(빌드 산출물)은 precache. 런타임 캐싱은 아래 두 가지만.
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
        navigateFallback: "index.html",
        runtimeCaching: [
          {
            // 학습 이미지(정적·다량) — 자주 안 바뀜 → CacheFirst.
            urlPattern: ({ url }) => url.pathname.startsWith("/learning-assets/"),
            handler: "CacheFirst",
            options: {
              cacheName: "learning-assets",
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // API 데이터는 신선도 우선 — 절대 캐시 금지(랭킹·데이터셋은 항상 서버 최신).
            urlPattern: ({ url }) => url.pathname.startsWith("/api/"),
            handler: "NetworkOnly",
          },
        ],
      },
      devOptions: {
        // dev 에서도 SW 동작 확인 가능(과하지 않게 기본만).
        enabled: false,
      },
    }),
  ],
  server: {
    proxy: {
      // dev 에서 same-origin 으로 호출 → 브라우저 CORS 회피. 운영은 VITE_API_BASE.
      "/api": { target: API_TARGET, changeOrigin: true },
      "/learning-assets": { target: API_TARGET, changeOrigin: true },
    },
  },
});
