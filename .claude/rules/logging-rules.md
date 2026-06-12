---
description: Logging rules for AgentGrid backend. SLF4J placeholder only, level thresholds (ERROR=operator action, WARN=auto-recovered anomaly, INFO=state transition/external call boundary), exception with stacktrace, no System.out/printStackTrace, no sensitive data. Loaded on every backend Java file edit. Trigger phrases - 로그 코드 작성·리뷰 시.
paths: ["backend/src/**/*.java"]
---

# Logging Rules (도메인 무관 코어 — 도메인 규칙은 코드 누적 후 추가)

> tbbe-hub 가 사후 일괄 로그 리팩토링 비용을 치른 교훈 — 첫 Java 파일부터 적용해 비용 0 으로.

## 레벨 기준

| 레벨 | 기준 | 예 |
|---|---|---|
| ERROR | 운영자 개입 필요 / 데이터 정합성 위협 | 분석 파이프라인 처리 불가, Outbox 발행 연속 실패 |
| WARN | 자동 복구된 이상 / 재시도 예정 | 외부 API 1회 실패 후 재시도, 타임아웃 후 폴백 |
| INFO | 상태 전이·외부 호출 경계·작업 단위 완료 | 제출 접수, 분석 시작/완료, 등급 산출 |
| DEBUG | 개발 진단 (운영 기본 비활성) | 중간 계산값, 페이로드 상세 |

## 필수

- SLF4J placeholder 만: `log.info("도구 분석 완료: toolId={}, grade={}", toolId, grade)` — 문자열 `+` 연결 금지
- 예외는 스택 포함: `log.error("분석 실패: toolId={}", toolId, e)` — 마지막 인자 예외 객체
- 1 작업 단위 = 1 결과 라인 원칙 (루프 내부 INFO 남발 금지 — 집계해서 1줄)
- Lombok `@Slf4j` 사용

## 금지

- `System.out.println` / `e.printStackTrace()` — 절대 금지
- 예외 삼키기 (catch 후 무로그 무전파)
- 민감정보 로깅: 토큰·API 키·자격증명 (제출된 repo URL 은 공개 정보라 허용)
- 같은 예외를 여러 레벨에서 중복 로깅 (잡은 곳에서 한 번만)
