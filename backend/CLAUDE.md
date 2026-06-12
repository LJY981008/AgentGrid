# backend/CLAUDE.md — Spring Boot 백엔드 특화 컨텍스트

> 루트 [CLAUDE.md](../CLAUDE.md) 의 공통 규칙이 우선. 이 파일은 백엔드 작업 시 추가 로드되는 특화 컨텍스트.
> 코딩 컨벤션은 [.claude/rules/backend-conventions.md](../.claude/rules/backend-conventions.md) (paths 자동 로드).

## 스택 (2026-06-12 확정)

- Java 21 (LTS) / Spring Boot **4.1.0** (2026-06-10 GA — 3.5는 2026-06-30 OSS 종료라 채택 안 함)
- Spring Framework 7.0.x / Jakarta EE 11 (Servlet 6.1, JPA 3.2) / Hibernate 7 / **Jackson 3 (`tools.jackson` 패키지 — 2.x와 다름 주의)**
- Gradle wrapper (start.spring.io 동봉 버전, 9.x 호환)
- 의존성: webmvc(구 web — Boot 4 명칭), data-jpa, postgresql, data-redis, amqp(RabbitMQ), validation, actuator, lombok, flyway

## ⚠️ Boot 4.x 주의사항

- 서드파티 라이브러리 추가 시 **Boot 4 호환 버전인지 개별 확인** (springdoc 등 — Jackson 3·모듈 분리 영향)
- Spring 공식 포트폴리오(Data/Security/AMQP)는 Boot BOM 이 버전 관리 — 직접 버전 명시 금지

## 로컬 개발

```bash
docker compose up -d          # 루트에서 — PG(:5432)/Redis(:6379)/RabbitMQ(:5672, UI :15672)
./gradlew bootRun             # backend/ 에서 — :8080 (compose 인프라 필요)
./gradlew bootTestRun         # compose 불필요 — Testcontainers 자동 기동 (TestAgentgridBackendApplication)
./gradlew test --no-daemon    # 통합 테스트 — TC 로 PG/MQ/Redis 기동 후 컨텍스트 검증 (~50s)
```

- DB 접속: `agentgrid` / `agentgrid-local` @ `localhost:5432/agentgrid` (compose.yaml 정의)
- `application.yml`: `ddl-auto: validate` — **스키마는 Flyway 로만** (`src/main/resources/db/migration/V{n}__{desc}.sql`)
- `open-in-view: false` — 트랜잭션 경계 밖 lazy 로딩 금지

## 자가 검증 루프 (Testcontainers 2.x)

- 구성: `src/test/java/com/agentgrid/TestcontainersConfiguration.java` — `@ServiceConnection` 으로 PG/RabbitMQ/Redis 자동 배선
- **컨테이너 이미지 = compose.yaml 과 버전 일치 의무** (postgres:18-alpine / rabbitmq:4.3-management-alpine / redis:8-alpine) — 환경 차이 거짓 통과 방지. 이미지 변경 시 양쪽 + 이 문서 동시 갱신
- TC 2.x 신명칭 주의: 아티팩트 `testcontainers-postgresql`, 패키지 `org.testcontainers.postgresql.*`
- 테스트 자동 실행은 opt-in: Stop 훅은 컴파일만, `CLAUDE_HOOK_TEST=1` 시 test 포함. CI 는 항상 full test

## 모니터링 (Actuator + Prometheus + Grafana)

- `/actuator/prometheus` 노출 (micrometer-registry-prometheus). 태그: `application=agentgrid-backend`
- 스택 기동: 루트에서 `docker compose --profile monitoring up -d` → Prometheus :9090 / Grafana :3001
- **지속 업데이트 규약**: 커스텀 메트릭(Counter/Timer/Gauge/@Timed) 추가 시 `infra/monitoring/grafana/dashboards/agentgrid-backend.json` 에 패널 동시 추가. 대시보드 7번 패널(RabbitMQ)은 도메인 코드 생기면 활성화됨
- 배포: `backend/Dockerfile` (multi-stage, JRE 21 alpine) — `--profile app`

## 아키텍처 방향 (기획서 4절 — 구현하며 구체화)

- 외부 리포지토리 스크래핑·헬스체크는 RabbitMQ 비동기 파이프라인
- 메시지 발행은 **Transactional Outbox** — 비즈니스 TX 내 OutboxEvent INSERT → 릴레이 발행 (직접 발행 금지)
- Consumer 멱등성 보장. 외부 호출은 타임아웃+재시도+서킷 브레이커 (Resilience4j 도입 시 이 파일 갱신)
- Redis: 디렉토리/인기 도구 캐싱 + 샌드박스 세션 (Phase 3)

## 작업 위임

- 구현·설계 리뷰: `backend-expert` 에이전트 / 스키마: `db-architect` 에이전트
- build.gradle 변경 시 이 파일도 같은 커밋에서 갱신 (harness-drift-check 가 감지)
