# test-engineer 메모리

- 베이스라인: AgentgridBackendApplicationTests (TC 통합 컨텍스트 로드, 실측 ~52s 통과 2026-06-12)
- TC 2.x: @ServiceConnection 3종(PG/RabbitMQ/Redis GenericContainer name="redis"), 이미지 compose 일치 의무
- 실행 정책: Stop 훅 컴파일만 / CLAUDE_HOOK_TEST=1 opt-in / CI full test
- 도메인 테스트 자산 계획: 등급 결정성·경계값 테스트, TS/Python 규칙 엔진 픽스처 repo 조각, Outbox·멱등성 패턴 — 구현 시작 시 픽스처 디렉토리 설계부터
