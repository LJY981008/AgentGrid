---
description: Python logging rules for stockpick. stdlib logging only (no print), module logger getLogger(__name__), level thresholds, no sensitive data (API keys), structured context for data-pipeline failures. Loaded on every Python edit. Trigger phrases - 로그 코드 작성·리뷰 시.
paths: ["src/**/*.py", "tests/**/*.py"]
---

# Logging Rules (Python — 초안)

> 도메인 전환 직후 초안. 코드 누적 시 실측 예시로 교체.

## 기본

- stdlib `logging` 만. 모듈 상단 `logger = logging.getLogger(__name__)`
- `print()` 금지 — 단 CLI/스크립트 진입점의 사용자 출력은 예외
- 포맷·핸들러 설정은 진입점에서 1회(라이브러리 코드는 핸들러 추가 금지)

## 레벨 기준

| 레벨 | 기준 | 예 |
|---|---|---|
| ERROR | 운영자 개입 필요 / 데이터 정합성 위협 | 일일 수집 전종목 실패, 백테스트 입력 불일치 |
| WARNING | 자동 복구된 이상 / 재시도 | 소스 차단 후 재시도, 일부 종목 결측 |
| INFO | 작업 단위 경계 | 벌크 수집 시작/완료, Top20 산출 완료, 룰 버전 적용 |
| DEBUG | 진단 (운영 비활성) | 팩터별 중간 점수, API 페이로드 |

## 필수

- f-string 보다 lazy 포맷 권장: `logger.info("수집 완료: market=%s, rows=%d", market, n)`
- 예외는 `logger.exception(...)`(스택 포함) 또는 `logger.error(..., exc_info=True)`
- 데이터 파이프라인 실패는 **분류 컨텍스트** 동반: 어느 소스·어느 종목·어느 날짜 (추적 가능)

## 금지

- 빈 except 후 무로그 / 같은 예외 중복 로깅 / 민감정보(TIINGO_API_KEY·EODHD_API_KEY 등 API 키) 로깅
- 루프 내 INFO 남발 — 집계해서 1줄 (전종목 루프는 진행률 DEBUG, 결과 INFO 1건)
