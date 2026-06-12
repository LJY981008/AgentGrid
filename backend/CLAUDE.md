# backend/CLAUDE.md — Spring Boot 백엔드 특화 컨텍스트

> 루트 [CLAUDE.md](../CLAUDE.md) 의 공통 규칙이 우선. 이 파일은 백엔드 작업 시 추가 로드되는 특화 컨텍스트.
> 코딩 컨벤션은 [.claude/rules/backend-conventions.md](../.claude/rules/backend-conventions.md) (paths 자동 로드).

## 스택 (2026-06-12 확정)

- Java 21 (LTS) / Spring Boot **4.1.0** (2026-06-10 GA — 3.5는 2026-06-30 OSS 종료라 채택 안 함)
- Spring Framework 7.0.x / Jakarta EE 11 (Servlet 6.1, JPA 3.2) / Hibernate 7 / **Jackson 3 (`tools.jackson` 패키지 — 2.x와 다름 주의)**
- Gradle wrapper (start.spring.io 동봉 버전, 9.x 호환)
- 의존성: web, data-jpa, postgresql, data-redis, amqp(RabbitMQ), validation, actuator, lombok, flyway

## ⚠️ Boot 4.x 주의사항

- 서드파티 라이브러리 추가 시 **Boot 4 호환 버전인지 개별 확인** (springdoc 등 — Jackson 3·모듈 분리 영향)
- Spring 공식 포트폴리오(Data/Security/AMQP)는 Boot BOM 이 버전 관리 — 직접 버전 명시 금지

## 로컬 개발

```bash
docker compose up -d          # 루트에서 — PG(:5432)/Redis(:6379)/RabbitMQ(:5672, UI :15672)
./gradlew bootRun             # backend/ 에서 — :8080
```

- DB 접속: `agentgrid` / `agentgrid-local` @ `localhost:5432/agentgrid` (compose.yaml 정의)
- `application.yml`: `ddl-auto: validate` — **스키마는 Flyway 로만** (`src/main/resources/db/migration/V{n}__{desc}.sql`)
- `open-in-view: false` — 트랜잭션 경계 밖 lazy 로딩 금지

## 아키텍처 방향 (기획서 4절 — 구현하며 구체화)

- 외부 리포지토리 스크래핑·헬스체크는 RabbitMQ 비동기 파이프라인
- 메시지 발행은 **Transactional Outbox** — 비즈니스 TX 내 OutboxEvent INSERT → 릴레이 발행 (직접 발행 금지)
- Consumer 멱등성 보장. 외부 호출은 타임아웃+재시도+서킷 브레이커 (Resilience4j 도입 시 이 파일 갱신)
- Redis: 디렉토리/인기 도구 캐싱 + 샌드박스 세션 (Phase 3)

## 작업 위임

- 구현·설계 리뷰: `backend-expert` 에이전트 / 스키마: `db-architect` 에이전트
- build.gradle 변경 시 이 파일도 같은 커밋에서 갱신 (harness-drift-check 가 감지)
