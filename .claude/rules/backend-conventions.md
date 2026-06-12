---
description: Java/Spring Boot coding conventions for AgentGrid backend. No wildcard import, no fully-qualified inline class names. Entity uses @NoArgsConstructor(PROTECTED) + @Builder. DTO uses record or static from(). All REST responses wrapped in ApiResult<T>. URL kebab-case plural. Constructor injection only. Loaded on every backend Java file edit. Trigger phrases - 백엔드 코드 작성·수정·리뷰 시.
paths: ["backend/src/**/*.java"]
---

# Backend Conventions (초안 — 개발하며 갱신)

> ⚠️ 프로젝트 미구현 상태의 초기 컨벤션. 실제 코드가 쌓이면 실측 예시로 교체하고
> 새 패턴 도입 시 이 파일을 같은 커밋에서 갱신한다 (`harness-drift-check` 가 감지).

## 기술 기준

- Java 21 / Spring Boot 4.1.x (Spring Framework 7, Jakarta EE 11)
- Base package: `com.agentgrid`
- 빌드: Gradle 9.x (`cd backend && ./gradlew build --no-daemon`)
- ⚠️ Boot 4.x 주의: Jackson 3 (`tools.jackson` 패키지), 서드파티 라이브러리는 Boot 4 호환 버전 확인 필수

## Import

- wildcard import 금지 (`import java.util.*` ❌)
- 본문 fully-qualified 클래스명 금지 — import 문으로 해결

## 레이어/패키지 구조 (초안)

```
com.agentgrid
├── <domain>/            # 도메인 단위 패키지 (registry, reliability, scraping ...)
│   ├── controller/      # REST 컨트롤러
│   ├── service/
│   ├── repository/
│   ├── domain/          # 엔티티, enum
│   └── dto/
├── global/
│   ├── config/
│   ├── exception/       # 전역 예외 처리 (ErrorCode enum + @RestControllerAdvice)
│   └── common/          # ApiResult 등 공통 응답
```

## API 설계

- URL: lowercase, kebab-case, 복수 명사 (`/api/tools`, `/api/reliability-reports`)
- 모든 응답은 `ApiResult<T>` 래퍼 (`data`, `message`, `timestamp`)
- 검증: `@Valid` + Bean Validation. 검증 실패는 전역 핸들러에서 일관 포맷으로

## Entity / DTO

- Entity: `@NoArgsConstructor(access = AccessLevel.PROTECTED)` + `@Builder`, setter 금지
- DTO: `record` 우선. 변환은 `static from(Entity)` / `toEntity()` 패턴
- 모듈 간 참조가 아닌 외부 도메인 ID 참조는 논리적 FK(`Long`) 고려 — 설계 시 db-architect 협의

## 의존성 주입

- 생성자 주입만 (`@RequiredArgsConstructor` + `private final`). 필드 주입 `@Autowired` 금지

## 신뢰성 원칙 (이 플랫폼의 정체성)

- 외부 호출(스크래핑, API)은 타임아웃 + 재시도 + 서킷 브레이커 필수 검토
- 메시지 발행은 Transactional Outbox 패턴 (직접 발행 금지 — 기획서 4절)
- Consumer 는 멱등성 보장 설계
- 예외는 삼키지 않는다 — 최소 로그 + 분류된 ErrorCode

## 스키마 변경

- Flyway 마이그레이션 파일로만 (`src/main/resources/db/migration/V{n}__{desc}.sql`)
- 직접 DDL 실행은 pre-bash-guard 가 차단함
