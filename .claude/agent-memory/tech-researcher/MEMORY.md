# tech-researcher 메모리

- 기준 리서치: `docs/research/2026-06-12-스택-버전-리서치.md` — Boot 4.1.0/Next 16.2.9/PG 18/Redis 8/RabbitMQ 4.3/Prometheus v3.12/Grafana 13.0.2 확정 근거
- Boot 4 호환 체크 패턴: Jackson 3(`tools.jackson`), Boot BOM 관리 의존성은 버전 직접 명시 금지, start.spring.io 프로브로 아티팩트 명칭 실측 가능 (TC 2.x 신명칭 발견 사례)
- 알려진 미해결: springdoc-openapi Boot 4 호환 — 첫 컨트롤러 작성 시 확인 예정
