# qa-tester 메모리

- 현황: 도메인 UI/API 0 — 검증 가능 대상은 스캐폴드 기본 페이지(:3000), actuator health(:8080), compose 헬스, Grafana(:3001)
- 백엔드 단독 기동: `./gradlew bootTestRun` (compose 불필요 — TC 자동)
- 시나리오 출처: docs/plans/2nd_plan.md 기능 명세(F1~F4) 수용 기준 — 구현되는 대로 E2E 시나리오로 승격
- 검증 서버 종료는 사용자 확인 후 (CLAUDE.md 하이브리드 제어권 규약)
