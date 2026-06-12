# frontend-expert 메모리

- Next.js 16.2.9 (App Router) + React 19.2.4 + TS strict + Tailwind 4. `output: "standalone"` (Docker)
- **코드 작성 전 frontend/AGENTS.md 규칙**: 이 Next 버전은 학습 데이터와 다를 수 있음 — `node_modules/next/dist/docs/` 동봉 문서 우선
- 사용자는 프론트 비전문(Spring 백엔드 전문) — 모든 결정을 백엔드 비유로 설명 (예: 서버 컴포넌트 ≈ 서버사이드 템플릿)
- API 베이스: 서버 컴포넌트는 `process.env.API_URL` (frontend/.env.example), 클라이언트 직접 호출 시 NEXT_PUBLIC_ 추가
- [Next16/Tailwind4 실측 함정](pitfalls-next16-tailwind4.md) — params 는 Promise(await 필수), globals.css 비레이어 body 규칙이 유틸리티보다 우선
- 2026-06-12 MVP 4화면 mock 프로토타입 구현됨 (`src/lib/mock/` = DTO 계약 초안, 커밋 93e5b1c) — conventions 실측 갱신 제안은 메인에 보고함
