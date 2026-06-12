@AGENTS.md

# frontend/CLAUDE.md — Next.js 프론트 특화 컨텍스트

> 루트 [CLAUDE.md](../CLAUDE.md) 의 공통 규칙이 우선. 위 `@AGENTS.md` import 는 Next.js 동봉 에이전트 규칙 —
> **이 버전(16.x)은 학습 데이터와 다를 수 있으므로 코드 작성 전 `node_modules/next/dist/docs/` 의 해당 가이드 확인 필수.**
> 코딩 컨벤션은 [.claude/rules/frontend-conventions.md](../.claude/rules/frontend-conventions.md) (paths 자동 로드).

## 스택 (2026-06-12 확정)

- Next.js **16.2.9** (App Router) / React 19.2.4 / TypeScript strict / Tailwind CSS 4 / ESLint 9
- 선택 근거: 공개 디렉토리형 사이트 = SEO 핵심 → 서버 렌더링 표준. 차선책이었던 Vite SPA 는 SEO 약점으로 보류
- Node 로컬 20.18 (Next 16 최소 20.9+ 충족 — 배포 시 Node 24 LTS 권장)

## 로컬 개발

```bash
npm run dev          # 개발 서버 :3000 (Turbopack)
npm run typecheck    # tsc --noEmit (Stop 훅 자동 실행)
npm run build        # 프로덕션 빌드
npm run lint         # ESLint
```

- 환경변수: `.env.example` 참조 (`API_URL` — 서버 컴포넌트 fetch 용). `.env` 는 gitignore
- 배포: `Dockerfile` (Next standalone — `next.config.ts` 의 `output: "standalone"` 전제) — 루트 `docker compose --profile app`

## 구조 (App Router)

- `src/app/` — 파일시스템 라우팅 (`page.tsx` = 페이지, `layout.tsx` = 공통 레이아웃)
- 백엔드 연동: 서버 컴포넌트에서 Spring Boot API(`:8080`) fetch — BFF 패턴. API 베이스 URL 은 env 로
- 공개 페이지(도구 디렉토리/상세/검색)는 SSR/ISR — SEO 가 이 서비스의 유입 핵심

## 사용자(백엔드 개발자)를 위한 핵심 비유

| 프론트 개념 | 백엔드 대응 |
|---|---|
| 서버 컴포넌트 | 서버사이드 템플릿 렌더링 (데이터 fetch 포함) |
| `src/app/tools/page.tsx` → `/tools` | `@GetMapping("/tools")` 의 파일시스템 버전 |
| `layout.tsx` | 공통 인터셉터/데코레이터 레이아웃 |
| Next 캐시/ISR | `@Cacheable` + TTL 재검증 |

## 작업 위임

- 구현·설계: `frontend-expert` 에이전트 (모든 결정에 비전문가 친화 설명 의무)
- package.json 의존성 변경 시 이 파일도 같은 커밋에서 갱신 (harness-drift-check 가 감지)
