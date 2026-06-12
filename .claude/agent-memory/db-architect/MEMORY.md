# db-architect 메모리

- PostgreSQL 18. 스키마 변경은 Flyway 만 (`backend/src/main/resources/db/migration/V{n}__{desc}.sql`) — 직접 DDL 은 pre-bash-guard 차단
- `ddl-auto: validate` — 엔티티/마이그레이션 불일치는 기동 실패로 표면화됨
- 도메인 데이터 요구: `docs/plans/2nd_plan.md` — 도구 메타데이터(수동 제출), 분석 결과(규칙 6축 + LLM 보정), 등급 이력, 카테고리. 리뷰는 Phase 2
- 관계형 무결성 우선, JSONB 는 분석 결과 원본 등 가변 구조 한정 (기획 원칙)
- 아직 마이그레이션 0건 — V1 설계가 첫 과업
