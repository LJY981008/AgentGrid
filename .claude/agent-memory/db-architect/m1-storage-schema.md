---
name: m1-storage-schema
description: M1 저장 스키마 핵심 결정 — Parquet 시장/연도 파티셔닝, PG18 테이블, 수정주가 조정계수 분리, PIT, 생존편향
metadata:
  type: project
---

M1 데이터 저장 스키마 설계 (2026-06-16, db-architect).

**Why:** stock-1st_plan §6 데이터 요구 + 미해결 #4(시계열DB) 결정. 생존편향·룩어헤드가 스키마 1급 요구(돈 걸림 BLOCKING).

**How to apply:** 후속 스키마 작업·python-expert 매핑 시 아래 결정 유지.

## 저장 분리 (리서치 확정)
- 벌크 백테스트 대량 스캔 = Parquet + DuckDB
- 운영 서빙·일일 증분 = PostgreSQL 18 (compose: DB/USER=stockpick, PW=stockpick-local, 18-alpine)
- TimescaleDB 비채택(일봉 ~3천만 행엔 과투자)

## Parquet 레이아웃
- 파티션: `market=KOSPI|KOSDAQ / year=YYYY` (Hive 스타일 디렉토리). 종목 파티션 안 함(폐지 누적 4~5천 종목 → 소파일 폭증, DuckDB 통계 무력화).
- 정렬: 파일 내 code, trade_date 로 정렬 적재 → DuckDB row-group min/max 프루닝.
- 수정주가는 raw OHLCV + adj_factor 동시 저장(원본 보존).

## PG18 테이블
- stock(종목마스터): code PK, delisted_at nullable(None=상장중) → 생존편향 방어.
- daily_bar: (code, trade_date) 복합 PK, trade_date RANGE 파티션(연도), BRIN(trade_date). raw OHLCV + adj_factor.
- (선택) investor_trade, short_sale: pykrx 보강, 동일 PIT 규약.
- top_entry / rule_version: 룰 버전·factors(JSONB) 이력 보존(재현성).

## 수정주가 (핵심 결정)
별도 테이블/이중 저장 아님. **raw OHLCV 단일 저장 + adj_factor(누적조정계수) 컬럼**. adjusted_close = close * adj_factor. 액면분할/배당 이벤트 변경 시 adj_factor 재계산만(원본 불변). 소스별 adjusted 정의 상이 문제를 자체 계산으로 통일.

## 룩어헤드(PIT) 보장
- 가격: trade_date ≤ t 만 조회(WHERE trade_date <= t). 일봉은 당일 마감 확정이라 trade_date 자체가 가용시점.
- 재무(공시 시차 핵심): financial 테이블에 fiscal_period(분기) + disclosed_at(공시일) 분리. 조회는 WHERE disclosed_at <= t. fiscal_period 로 조회하면 룩어헤드(미공시 재무 누설).
- adj_factor 는 미래 분할 반영분이라 백테스트 PIT 위반 소지 → as_of 스냅샷 or 시점 재계산 주의(open question).

## 마이그레이션
도구 미정. alembic ADR 권고(raw SQL 병용). [[feedback-migration-tooling]]
