---
name: s5a-pg-schema-design
description: S5-a PG18 스키마(stock·ticker_history·daily_bar) + alembic 첫 마이그레이션 + Parquet→PG 단방향 동기 설계 결정
metadata:
  type: project
---

S5-a 적재안전성 설계 (2026-06-18, db-architect). S5 4분해 중 첫 단계(a 적재안전성 → b 종목마스터채움 → c 벌크오케스트레이션 → d 실UniversePort+S6게이트).

**Why:** 종목마스터 PG/alembic 저장 확정(ADR-001 첫 실사용). 생존편향·룩어헤드가 스키마 1급(돈 걸림).

**How to apply:** S5-b/c/d 및 python-expert 매핑 시 아래 유지. 마이그레이션 파일·코드는 미생성(설계만).

## 핵심 결정
- **3테이블 첫 마이그레이션 1개**(create_core_tables): stock·ticker_history·daily_bar. financial 은 범위 밖(현 Parquet/JSON 처리 중).
- **alembic + psycopg3**(psycopg[binary], psycopg2 아님). 디렉토리 `/migrations/`(src 밖·인프라). env.py 가 compose DATABASE_URL 읽되 `postgresql+psycopg://` 변환. alembic.ini 패스워드 하드코딩 금지. compose app volumes 에 ./migrations 마운트 추가 필요(현재 없음). PG18 고급기능(파티션·BRIN·ENUM·CHECK·EXCLUDE)은 op.execute() raw SQL.

## EODHD 명세가 강제한 것 (실측 — exchange-symbol-list 응답=Code/Name/Country/Exchange/Currency/Type/Isin)
- CIK 미제공 → cik 출처는 EDGAR(현재스냅샷만, 폐지·ETF·외국주 미해소 다수)
- 폐지일(date) 미제공 → delisted_at 은 마지막 EOD 거래일 추론(S5-b)
- 거래소 US통합코드 권장 → exchange 정밀구분 약함

## 스키마 (실측 storage.py 정밀도 일치)
- stock: **surrogate BIGINT id PK + cik nullable UNIQUE** 권고(R1 미결 — 사용자는 "cik PK" 확정했으나 cik 미해소 폐지종목 적재불가=생존편향누수라 충돌. 사용자 결정요청). exchange_enum(types 6값). delisted_at nullable + delisted_at_source. DELETE 금지는 rule/리뷰 봉인(트리거 과투자).
- ticker_history: PK(stock_id,ticker,valid_from), valid_to nullable. PIT조인=valid_from<=trade_date<valid_to. EXCLUDE(btree_gist) ticker 구간중첩금지는 S5-b 채움과 동반 이월 권고.
- daily_bar: PARTITION BY RANGE(trade_date) 연도별, PK(ticker,trade_date), NUMERIC(38,10)가격/(38,12)adj_factor=storage.py scale 정확일치. CHECK(OHLC·양수가격·adj>0)=storage.py DuckDB게이트와 1:1 동형(PG=2차방어선). BRIN(trade_date). DEFAULT 파티션 안전망.

## D2/D3/D5 결정
- D2(FK): daily_bar→stock **직접 FK 안 함**(ticker는 시변 N:1·벌크COPY성능·1인). 사후검증쿼리(고아 ticker 탐지)로 대체.
- D3(파티션): 연도RANGE 수동(pg_partman 안 씀·1인). 데이터범위(~1995-2026 30개) 마이그레이션 일괄생성+DEFAULT.
- D5(동기): **단방향 Parquet(1차진실)→PG(파생서빙)**. DuckDB→PG COPY/ON CONFLICT UPSERT(PK 멱등). PG 직접수정 금지(역류=오염). 일1회 충분(랭킹은 배치). 실벌크=S5-c.

## G1 read-merge-write 순서 (BLOCKING)
현 write_daily_bars 는 (ticker,year) 통파일 덮어쓰기(소실위험, M1§7 이월). G1=read→merge(ticker,trade_date dedup·신규우선)→write(temp→rename). 벌크순서: fetch→write(G1)→verify_parquet(expected=merge결과)→**PASS시에만** PG동기→PG사후검증. Parquet게이트 FAIL시 PG미반영(stale<손상). expected 는 병합후 전체기준.

[[m1-storage-schema]] [[feedback-migration-tooling]]
