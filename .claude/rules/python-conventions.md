---
description: Python coding conventions for stockpick (US stock analysis — NYSE/NASDAQ/AMEX). Python 3.12+ strict typing, no any, explicit failure reporting (no bare/broad except), evidence-based fix discipline, survivorship-bias & look-ahead avoidance in data/backtest code. Loaded on every Python edit. Trigger phrases - 코드 작성·수정·리뷰 시.
paths: ["src/**/*.py", "tests/**/*.py", "pyproject.toml"]
---

# Python Conventions (초안 — 개발하며 갱신)

> ⚠️ 도메인 전환 직후 초안. 실제 코드가 쌓이면 실측 예시로 교체하고 새 패턴 도입 시 같은 커밋에서 갱신 (harness-drift-check 감지).

## 기술 기준

- Python ≥3.12 / **uv** 패키지·환경 관리 / src 레이아웃(`src/stockpick/`)
- 검증: `ruff check` + `ruff format --check` + `mypy`(strict) + `pytest` — Stop 훅 자동(도구 설치 시)
- 런타임 의존성은 `uv.lock` 실측 고정(현재: duckdb·httpx·pyarrow·fastapi·uvicorn[standard]·**alembic·psycopg[binary]**(S5-a PG)) — 추측 고정 금지
- **PG 스키마 변경 = alembic 마이그레이션만**(`migrations/versions/`·[ADR-006]·`alembic upgrade head`). 직접 DDL 금지. PG18 기능은 raw SQL(op.execute). PG=파생 서빙(단방향 Parquet→PG·`data/db.py`), 직접 수정 금지

## 모듈 경계 (위반 금지 — AI 자동화 미래 확장 보존)

```
data    수집·저장·정규화   (Tiingo 파일럿→EODHD 벌크 + SEC EDGAR 재무(PIT), Parquet+PG)
rules   Top20 정량 랭킹    (data 의존, backtest 검증 통과한 것만)
backtest 룰 검증           (data 의존)
api/cli/webapp            상위 — data/rules/backtest 조합 (M3+)
```
- 하위(data/rules/backtest)는 상위(api·webapp)를 import 하지 않는다
- 도메인 계약 타입 원본 = `src/stockpick/types.py` (기획 §6 동기)

## 타입

- `mypy --strict` 통과. `Any` 금지(`object`+narrowing 또는 명확 타입). `from __future__ import annotations`
- 외부 입력(API 응답·CSV·env)은 경계에서 검증 후 내부 타입화. 누락 필드 = 명시적 `None`, 추측값 채움 금지

## 에러 처리 (핵심 원칙 — stock-1st_plan §4.1)

- **실패를 명확히 보고** — 조용히 깨진 데이터 저장/반환 금지
- `except:`(bare)·광역 `except Exception:` 후 무시 금지 (ruff BLE). 최소 분류·로그·재던지기
- 데이터 실패는 사유 분류: 결측·소스차단·파싱오류 — 추적 가능하게

## ⚠️ 금융 데이터 특화 (BLOCKING — 돈 걸림)

- **생존편향 회피**: 백테스트·랭킹은 폐지 종목 포함(`Stock.delisted_at`). 현재 상장 종목만으로 과거 수익률 계산 금지
- **룩어헤드 금지**: 특정 시점 랭킹에 그 시점 이후 데이터 사용 금지(미래 정보 누설). 시점 t 결정엔 ≤t 데이터만
- **수정주가 정의 통일**: 소스별 adjusted 정의 상이 — 단일 기준 + 액면분할 교차검증
- **백테스트 검증 전 룰 신뢰 금지**: 정량 룰은 backtest 통과 후에만 운영. 과적합 경고

## 로깅

- 표준 `logging` 모듈, 모듈별 `logger = logging.getLogger(__name__)`. print 금지(스크립트 진입점 제외)
- 상세는 [logging-rules](logging-rules.md)
