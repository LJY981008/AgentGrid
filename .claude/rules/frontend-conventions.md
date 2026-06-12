---
description: React/Next.js/TypeScript conventions for AgentGrid frontend. App Router, server components by default, TypeScript strict, Tailwind CSS 4. Loaded on every frontend source edit. Trigger phrases - 프론트 코드 작성·수정·리뷰 시.
paths: ["frontend/src/**"]
---

# Frontend Conventions (초안 — 개발하며 갱신)

> ⚠️ 프로젝트 미구현 상태의 초기 컨벤션. 실제 코드가 쌓이면 실측 예시로 교체하고
> 새 패턴/라이브러리 도입 시 이 파일을 같은 커밋에서 갱신한다.

## 기술 기준

- Next.js 16.2.x (App Router) / React 19.2.x / TypeScript strict / Tailwind CSS 4
- ⚠️ **코드 작성 전 `frontend/AGENTS.md` 준수**: 이 Next.js 버전은 학습 데이터와 다를 수 있음 —
  `node_modules/next/dist/docs/` 의 동봉 문서를 먼저 확인
- 검증: `cd frontend && npm run typecheck` (Stop 훅이 자동 실행)

## 컴포넌트

- 서버 컴포넌트 기본. `"use client"` 는 상호작용(이벤트/상태) 필요한 leaf 에만
- 함수형 컴포넌트만. 파일명 = 컴포넌트명 PascalCase (`ToolCard.tsx`)
- 페이지/레이아웃은 App Router 규약 (`src/app/**/page.tsx`, `layout.tsx`)

## 데이터 페칭

- 공개 페이지(디렉토리/상세): 서버 컴포넌트에서 Spring Boot API `fetch` + Next 캐시/ISR — SEO 핵심
- 클라이언트 상호작용 데이터: 도입 시 TanStack Query 검토 (도입 결정되면 이 파일 갱신)
- API 베이스 URL 은 환경변수 (`process.env`) — 하드코딩 금지

## 타입

- `any` 금지. API 응답 타입은 백엔드 `ApiResult<T>` 구조와 1:1 인터페이스 정의
- 백엔드 DTO 변경 시 프론트 타입 동기 갱신 (드리프트 주의)

## 스타일

- Tailwind 유틸리티 우선. 커스텀 CSS 는 최후 수단
- 디자인 토큰/공통 컴포넌트가 생기면 `src/components/ui/` 로 격리 (생기면 이 파일 갱신)

## 백엔드 개발자(사용자)를 위한 메모

- 서버 컴포넌트 ≈ 서버 사이드 템플릿 렌더링 (Thymeleaf 와 유사한 위치, 단 React 문법)
- App Router 디렉토리 = URL 매핑 (`src/app/tools/page.tsx` → `/tools`) — `@RequestMapping` 의 파일시스템 버전
