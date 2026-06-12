# security-reviewer 메모리

- 도메인 위협 모델 핵심: 신뢰할 수 없는 외부 repo 를 받아 분석하는 플랫폼 — ① repo URL SSRF ② 악성 repo(zip-bomb/traversal) ③ **클론 코드 비실행 원칙**(2nd_plan 확정) ④ LLM 보정 프롬프트 인젝션(악성 README 로 등급 조작) ⑤ 제출 어뷰징
- 분석 격리 방식은 기획 미해결 질문 #3 — 결정 시 위협 모델 재검토 필요
- 시크릿 현황: 로컬 기본값(agentgrid-local)만 하드코딩 허용, 실 시크릿은 .env(.example 에 자리만)
