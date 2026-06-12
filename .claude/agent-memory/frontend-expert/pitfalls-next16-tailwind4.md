---
name: pitfalls-next16-tailwind4
description: Next 16 / Tailwind 4 에서 학습 데이터와 다른 실측 확인된 함정 2건 (2026-06-12 프로토타입 구현 중 검증)
metadata:
  type: project
---

# Next 16 / Tailwind 4 실측 함정

1. **동적 라우트 `params` 는 `Promise`** — `page.tsx`/`generateMetadata` 시그니처가
   `{ params: Promise<{ slug: string }> }` 이고 반드시 `await params`. 클라이언트 페이지에서는 `use(params)`.
   근거: `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/dynamic-routes.md` 실측.
2. **Tailwind 4 레이어 우선순위**: `globals.css` 의 비레이어 `body { background: ... }` 규칙은
   `@layer utilities` 의 유틸리티 클래스보다 **항상 우선**. body 스타일을 바꾸려면 유틸리티가 아니라
   CSS 변수(`--background` 등) 쪽을 수정해야 한다.

**How to apply:** 프론트 코드 작성/리뷰 시 이 두 패턴이 보이면 학습 데이터 기준으로 "고치지" 말 것.
