---
title: webapp 스택 버전·API 표면 실측 (Vite+React PWA / FastAPI)
date: 2026-06-17
tags: [research, webapp, frontend, fastapi, 버전핀]
상태: 현행
출처기준일: 2026-06-17
---

# webapp 스택 버전·API 표면 실측 (2026-06-17)

> stockpick 웹앱(PWA 대시보드, M4) + API 층 착수용. 1인 로컬 대시보드(로컬 FastAPI 소비).
> ⚠️ 학습데이터 불신 — registry.npmjs.org / pypi.org JSON + 공식문서 실측. 각 결론 2개+ 출처.
> registry.npmjs.org JSON API 사용(npmjs.com 웹 페이지는 WebFetch 403).

---

## A. 프론트 버전 핀 (package.json 그대로 사용 가능)

| 패키지 | 2026-06-17 최신 안정 | 비고 / 함정 | 출처 |
|---|---|---|---|
| `vite` | **8.0.16** | engines.node `^20.19.0 \|\| >=22.12.0` — Node 22/24 LTS 권장 | registry.npmjs.org/vite/latest |
| `@vitejs/plugin-react` | **6.0.2** | peer `vite ^8.0.0` — Vite 8과 정합(메이저 핀) | registry.npmjs.org/@vitejs/plugin-react/latest |
| `react` | **19.2.7** | React 19 현행. StrictMode 이중호출·use() 훅 등 | registry.npmjs.org/react/latest |
| `react-dom` | **19.2.7** | react와 버전 동기 | registry.npmjs.org/react-dom/latest |
| `typescript` | **6.0.3** | TS 6 메이저(기존 5.x 아님) | registry.npmjs.org/typescript/latest |
| `@types/react` | **19.2.17** | react 19 대응 | registry.npmjs.org/@types/react/latest |
| `react-router` | **7.18.0** | ⚠️ v7 패키지 통합 — `react-router-dom` 불요 | registry.npmjs.org/react-router/latest |
| `vite-plugin-pwa` | **1.3.0** | peer vite `...\|\| ^8.0.0` (Vite 8 포함), workbox-build/window `^7.4.1` | registry.npmjs.org/vite-plugin-pwa/latest |
| `react-markdown` | **10.1.0** | ⚠️ v10 — `urlTransform` prop 방식(아래) | registry.npmjs.org/react-markdown/latest |
| `remark-gfm` | **4.0.1** | 표·체크박스·취소선 | registry.npmjs.org/remark-gfm/latest |
| `rehype-slug` | **6.0.0** | heading id 부여 | registry.npmjs.org/rehype-slug/latest |
| `recharts` | **3.8.1** | peer react `^16.8 \|\| 17 \|\| 18 \|\| 19` — React 19 OK | registry.npmjs.org/recharts/latest |

- 스캐폴딩 명령: `npm create vite@latest webapp -- --template react-ts` (현행 react-ts 템플릿)
- Node: **v24 (Krypton) Active LTS = 24.16.x**, v22 (Jod)는 Maintenance LTS. v20/v18 EOL.
  컨테이너 베이스: `node:24` 또는 `node:22`. (출처: nodejs.org/en/about/previous-releases)

---

## B. 백엔드 버전 핀 (pyproject 그대로 사용 가능)

| 패키지 | 2026-06-17 최신 | 비고 / 함정 | 출처 |
|---|---|---|---|
| `fastapi` | **0.137.1** | requires `pydantic>=2.9.0`, `starlette>=0.46.0` | pypi.org/pypi/fastapi/json |
| `uvicorn[standard]` | **0.49.0** | ASGI 서버 (`[standard]` extra) | pypi.org/pypi/uvicorn/json |
| `starlette` | **1.3.1** | ⚠️ 1.0 메이저 — FastAPI 0.137.1이 직접 1.3.1 핀(아래) | pypi.org/pypi/starlette/json + FastAPI 릴리스노트 |
| `pydantic` | **2.13.4** | v2 (2026-05-06 릴리스) | pypi.org/pypi/pydantic/json |

---

## C. ⚠️ API 표면 함정 — 현행 올바른 사용법

### C-1. react-router v7 (메이저 변동 큼)
- **패키지 통합**: v7는 `react-router-dom` 불필요 — 전부 `react-router`에서 import.
  단 DOM 의존 API(`RouterProvider`, `HydratedRouter`)는 deep import `react-router/dom`.
  (출처: reactrouter.com/upgrading/v6 — "no longer need react-router-dom")
- **모드 선택**: 본 프로젝트는 client-only SPA(SSR 없음) → **Data Mode** 권장
  (`createBrowserRouter` + `RouterProvider`). Framework Mode(routes.ts·Vite plugin·SSR)는 오버킬.
- 현행 형태:
  ```
  import { createBrowserRouter } from "react-router";
  import { RouterProvider } from "react-router/dom";
  const router = createBrowserRouter([{ path: "/", Component: Root, loader }]);
  <RouterProvider router={router} />
  ```
  (출처: reactrouter.com/start/modes, api.reactrouter.com/v7 createBrowserRouter)

### C-2. vite-plugin-pwa — workbox runtimeCaching
- `generateSW`(기본) 전략에서 `workbox.runtimeCaching` 배열로 런타임 캐시 정의.
- 각 항목: `urlPattern`(정규식/함수) + `handler`(`NetworkFirst`/`CacheFirst`/`NetworkOnly`/`CacheOnly`/`StaleWhileRevalidate`) + `options`(cacheName/expiration/cacheableResponse).
- 본 프로젝트 권장: **API 응답(로컬 FastAPI)은 `NetworkFirst`**(networkTimeoutSeconds) 또는 항상-신선이 필수면 `NetworkOnly`.
  정적 이미지(docs/learning)는 `CacheFirst`.
  ```
  workbox: { runtimeCaching: [{
    urlPattern: /\/api\//, handler: 'NetworkFirst',
    options: { cacheName: 'api-cache', networkTimeoutSeconds: 10 }
  }]}
  ```
  (출처: vite-pwa-org.netlify.app/workbox/generate-sw, deepwiki vite-plugin-pwa caching-strategies)
- ⚠️ runtimeCaching은 `generateSW`에서만 동작 — `injectManifest`(커스텀 SW) 쓰면 무시됨(공통 함정).

### C-3. react-markdown v10 — 상대경로 src/href 재작성
- **커스텀 rehype 플러그인보다 `urlTransform` prop이 현행 권장 방법.**
  ```
  <Markdown urlTransform={(url, key, node) =>
    key === 'src' ? `/api/learning-images/${url}` : url
  } remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]} />
  ```
  - `urlTransform(url, key, node)` — `key`는 `'src'`/`'href'` 등 속성명. 상대경로를 백엔드 절대경로로 치환.
  - ⚠️ 보안: urlTransform을 느슨하게 덮으면 XSS 벡터 열림 — 기본은 http/https/mailto/상대만 허용(secure by default). 치환 시 프로토콜 화이트리스트 유지.
  (출처: npmjs.com/package/react-markdown[v10 readme], remarkjs/react-markdown changelog)
- 커스텀 rehype가 필요하면 `unist-util-visit`로 hast tree 순회(`visit(tree, 'element', node => ...)`)하나, 단순 URL 재작성엔 불요.

### C-4. FastAPI StaticFiles / CORS (현행 시그니처)
- StaticFiles (docs/learning 이미지 정적 서빙):
  ```
  from fastapi.staticfiles import StaticFiles
  app.mount("/static", StaticFiles(directory="static"), name="static")
  ```
  (`fastapi.staticfiles`는 starlette wrapper — `starlette.staticfiles`와 동일)
- CORS (localhost:5173 Vite dev):
  ```
  from fastapi.middleware.cors import CORSMiddleware
  app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
  ```
  - ⚠️ `allow_credentials=True`면 `allow_origins=["*"]` 금지 — 명시 origin 필수.
  - dev에서는 **Vite proxy(`server.proxy`)로 same-origin 처리하면 CORS 자체가 불필요** — 둘 중 택1 권장(proxy 우선).
  (출처: fastapi.tiangolo.com/tutorial/cors, /tutorial/static-files, vite.dev/config/server-options)
- Vite proxy 예: `server: { proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } } }`

### C-5. TestClient / dependency_overrides (테스트 패턴)
- `from fastapi.testclient import TestClient`(starlette 기반), `client = TestClient(app)`.
- 의존성 교체: `app.dependency_overrides[get_db] = override_get_db` — 테스트 후 `app.dependency_overrides.clear()`.
  (현행 유지 — FastAPI 공식 테스트 튜토리얼 패턴. 라이브 데이터 의존 금지 규칙과 정합)

---

## Caveats (미확인 · 시점 민감)

- **Starlette 1.0 메이저 함정**: Starlette 최신 단독은 1.3.1이고 1.0은 lifespan 전환·TemplateResponse 시그니처 변경 등 breaking 존재(FastAPI Discussion #15198 unhashable type:dict 사례). **단 FastAPI 0.137.1이 starlette 1.3.1을 직접 핀**하므로 FastAPI 경유 사용은 안전. `starlette`를 별도 직접 핀하지 말고 fastapi가 끌어오게 둘 것. Jinja2 TemplateResponse를 직접 쓸 일 없으면 영향 없음(본 API는 JSON 위주). (출처: starlette.dev/release-notes, simonwillison.net 2026-03-22)
- **TypeScript 6 / React 19 / Vite 8 / TS-router 7 모두 메이저 상향** — 학습데이터(5.x/18/5.x/6.x) 기준 코드 패턴 추측 금지. 특히 react-router는 v6→v7에서 import 경로·모드 개념이 크게 바뀜.
- 버전은 2026-06-17 latest 스냅샷 — M4 착수 시점에 재확인 필요(특히 마이너 패치). `package.json`엔 캐럿(^) 핀 권장하되 메이저 고정 의도면 메이저 명시.
- recharts 3.x는 백테스트 곡선용(M4 후반) — 본격 사용 전 차트 컴포넌트 API(3.x BarChart/LineChart props) 별도 실측 권장.
- `vite-plugin-pwa` peer가 Vite 8 포함을 확인했으나, workbox-build 7.4.1 동반 설치 필요 — `npm i` 시 자동 해소되는지 lockfile로 검증 권장.
- ⚠️ 코드/설정 미작성(리서치 한정). 실제 적용은 frontend-expert / python-expert / devops-engineer.

## 후속 (HOME.md MOC)
- 본 문서를 `docs/HOME.md` 🔬 리서치 섹션에 링크 추가 필요(drift 강제).
