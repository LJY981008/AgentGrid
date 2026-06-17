---
description: Web app (PWA) conventions for stockpick frontend. Personal 1-user dashboard - Top20/Top5 view, portfolio tracking, rule/backtest results. Mobile-first responsive PWA, server API consumed read-mostly. Loaded on webapp edits. Trigger phrases - 웹앱·프론트·화면·대시보드·PWA 작성 시.
paths: ["webapp/**"]
---

# Web App (PWA) Conventions — M3 활성 (실측 2026-06-17)

> 웹앱은 M3 부터 구현됨. 스택 확정·구조는 아래 실측 반영. 5화면 전부 구현 — `BacktestPage`는 `/api/backtest` 소비·Recharts 자산곡선(골격·미검증경고 상시).

## 방향 (stock-1st_plan §7)

- **개인 1인용 대시보드** — Top20/Top5 뷰, 분산투자 현황·수익률, 추적 기록, 룰 버전·백테스트 결과
- **모바일 우선 반응형 + PWA** (홈 화면 추가, 앱처럼). Android 네이티브 폐기 결정(§3-2)
- 서버(Python API)를 소비하는 **읽기 위주** — 실거래·주문 없음(비목표)

## 확정 스택 (research/2026-06-17-webapp-stack-버전)

- **Vite 8 + React 19 + TypeScript(strict)** — `webapp/`, `npm` (uv 아님). Node 22.
- 라우팅 `react-router 7`(Data Mode, `src/router.tsx`) · 마크다운 `react-markdown 10` + `remark-gfm` + `rehype-slug` · PWA `vite-plugin-pwa`(generateSW)
- 차트: 이산값(랭킹 등)은 **순수 CSS 막대(div width%)**. **시계열 곡선(백테스트 자산곡선)은 Recharts ^3.8.1**(React19 호환·도입됨). 신규 곡선은 Recharts, 단순 막대는 CSS 유지(의존성 절제)

## 구조 (실측)

| 경로 | 역할 |
|---|---|
| `src/api/{client,endpoints,types,useApi}.ts` | API 클라이언트. `types.ts` = `src/stockpick/api/models.py` **1:1 미러**(단일 출처는 서버) |
| `src/pages/` | `Dashboard`(랭킹·홈) · `Data`(수집 트리거) · `Universe`(종목 목록) · `Learning`(docs/learning 렌더) · `Backtest`(자산곡선 Recharts·지표·벤치·미검증경고) · `NotFound` |
| `src/components/` | `Layout` · `common/{Badge,StateViews,UnvalidatedWarning}` · `ranking/RankingTable` · `learning/{TopicTree,MarkdownView}` |
| `vite.config.ts` | dev proxy `/api`·`/learning-assets` → `VITE_DEV_API_TARGET`(컨테이너 app:8000) + vite-plugin-pwa |

## 원칙 (BLOCKING)

- 데이터는 서버 API(`/api/...`)에서. 프론트에 투자 로직(랭킹·점수·팩터) **중복 금지** — 서버가 단일 진실. 프론트는 표시·트리거만
- ⭐ **§4.1**: 랭킹은 백테스트 미검증 = 알파 아님. `meta.validated:false` → `UnvalidatedWarning` 배지 **상시 노출**(fail-safe — 응답 누락 시에도 경고 쪽으로). 제거 금지
- ⚠️ `POST /api/ingest` 는 **라이브 EODHD 무료티어(20콜/일) 소비** — 버튼에 고지 + 429 응답은 "한도 초과(리셋 후)" 친화 표시
- 빈 상태(데이터 없음): 대시보드 entries=[] → "데이터 수집 먼저" 안내 + DataPage 유도(첫 실행 UX)
- 학습 이미지: 상대경로 → `/learning-assets/...` 재작성(`MarkdownView` urlTransform). 절대 URL 미변경. `loading=lazy`
- API 베이스·키는 env(`VITE_DEV_API_TARGET`). 하드코딩 금지. 키·토큰을 프론트 번들에 넣지 않음
- 타입 안전: `tsconfig strict`. `any` 회피 — 서버 계약을 `types.ts` 로 정확히 미러
- 빌드 캐시(`*.tsbuildinfo`)·`node_modules`·`dist`·PWA 생성물(`sw.js`·`workbox-*`)은 커밋 금지(`webapp/.gitignore`)

## 검증

- 타입체크+빌드: `npm run build`(컨테이너 web 또는 로컬 node:22). CI(.github/workflows/ci.yml)에 webapp 잡 포함
- 풀스택: `docker compose up -d` → 브라우저 http://localhost:5174, API http://localhost:8000

## 사용자를 위한 메모

- **사용자(백엔드 전문, 프론트 비전문)** — 결정은 백엔드 비유로 설명, 단순 구조 우선
- PWA = 웹인데 폰 홈에 설치돼 앱처럼 뜨는 것. 별도 앱스토어 배포·네이티브 빌드 불필요 — 1인 유지보수 최선
- 서버=단일 진실, 프론트=얇은 뷰 = Spring 의 `@RestController` ↔ 타임리프/SPA 분리와 동일 사고
