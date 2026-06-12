---
name: open-questions-status
description: 미해결 질문 현황 — #1/#2/#3/#6/#8 확정(2026-06-12, 3rd_plan), 잔여 #4/#5/#7 + 신규 #9/#10. 다음 단계 = DB 스키마 설계
metadata:
  type: project
---

2026-06-12 미해결 질문 #1(시드 캘리브레이션 1회 후 동결), #2(claude-sonnet-4-6, 월 $30), #3(격리 2단계), #6(rate limit, CAPTCHA 없음), #8(풀 4화면) 사용자 확정 — `docs/plans/3rd_plan.md` 에 기록 완료, PLAN_STATUS·HOME 동기화 완료.

**Why:** 5건 확정으로 DB 스키마에 영향 주는 결정이 전부 닫힘 → 3rd_plan §4 에서 db-architect 착수 조건 충족 선언 (전달 요구사항 7항 명시).

**How to apply:** 잔여 질문은 5건 — #4 재분석 주기(Phase 2), #5 카테고리(M4 전), #7 이의 제기(Phase 2), 신규 #9 Python 스폿 체크 불일치 처리(M3 중반), #10 LLM 예산 소진 건 소급 보정(M3 전). 전부 스키마 비차단. 후속 기획 시 3rd_plan §3 이 기준. 결정 5건은 "변경 금지" — 재론 요청 시 사용자 재확정 필요. M2→M3 사이에 캘리브레이션 게이트 존재 (미통과 시 M3 시작 금지).
