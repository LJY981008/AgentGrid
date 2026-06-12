# backend-expert 메모리

- Spring Boot 4.1.0 / Java 21 / Gradle 9.5.1. **Boot 4 주의**: Jackson 3 (`tools.jackson`), 스타터 명칭 변경(webmvc, per-module test starter), 서드파티 호환 개별 확인
- Testcontainers 2.x: 아티팩트 `testcontainers-postgresql` 등 신명칭, 패키지 `org.testcontainers.postgresql.*`. `./gradlew bootTestRun` = compose 없이 앱 실행
- 테스트 컨테이너 이미지는 compose.yaml 과 버전 일치 의무 (postgres:18-alpine / rabbitmq:4.3-management-alpine / redis:8-alpine)
- 메트릭: micrometer-prometheus 활성 (`/actuator/prometheus`). 커스텀 메트릭 추가 시 Grafana 대시보드(infra/monitoring/grafana/dashboards/) 갱신 의무
- 아직 도메인 코드 0 — 첫 구현 시 `.claude/rules/backend-conventions.md` 초안을 실측 예시로 갱신할 것
