# ADR-007: 백테스트 라이브 실용화 — DuckDB 단일 컬럼 스토어 + momentum 부분 푸시다운

- **날짜**: 2026-06-22
- **상태**: 승인
- **결정자**: 사용자 / Claude 협의 (PoC 실측 + critic 적대적 리뷰 REVISE 반영)
- **관련**: [[ADR-004-백테스트-프레임워크-자체구현]](성능 병목 시 재검토 트리거 발동)·[[ADR-006-PG스키마-alembic-첫실사용]](Parquet 1차원본·단방향 파생 철학)·[[2026-06-22-S6a-full_series-OOM수정]]·[[2026-06-22-백테스트-라이브실용화-DuckDB컬럼스토어]]

## 맥락 (Context)

S6-a 가 `full_series` 메모리 OOM 을 `load_range` 로 해소했으나 라이브 `/api/backtest`(50,184 종목·5.1G·1억행) 가 **load_range 매 리밸 풀스캔 30초·라이브 21분+ 미완**. 근본 = Parquet ticker 가 파일명(`exchange=/year=/{ticker}.parquet`·578,330 파일)이라 DuckDB ticker 프루닝 불가 → 매 쿼리가 window year 의 수만 파일 풀스캔. 라이브 백테스트 미실행 = S6-b 신뢰성 게이트·`validated=true` 불가. PoC 실측으로 해법 확정.

## 결정 (Decision)

**Parquet→`cache.duckdb` 단일 컬럼 스토어(파생) + momentum 부분 푸시다운(SQL 끝점 추출·Python Decimal 나눗셈).**

1. **`.duckdb` = 파생 캐시(재생성·단방향)**: Parquet 는 1차 진실원본 불변(ADR-006 철학 동일). `base_dir/cache.duckdb` 단일 컬럼 table 을 `bulk --finalize` 후처리에서 멱등 재생성(원자적 temp→`os.replace`·반쪽 부패 방지). 부재/부패 시 `_select_price_port` 가 `ParquetPriceSeriesPort` 폴백(기능 회귀 0·속도만 캐시 의존). ⚠️ **속도 근원 = 578k 파일 glob → 단일 컬럼 스토어**(SEQ_SCAN 컬럼 스캔). `(ticker,trade_date)` 인덱스는 **EXPLAIN ANALYZE 효용 확인 후만**(critic MAJOR-1 — DuckDB ART 인덱스가 `=ANY`/window 에 미사용 SEQ_SCAN 관측 → 미사용이면 제거).

2. **momentum 부분 푸시다운(완전 SQL 아님)**: SQL(`data/duckdb_cache.momentum_endpoints`)이 `ROW_NUMBER() PARTITION BY ticker`·`COUNT(*) OVER`·`WHERE trade_date<=$as_of`(룩어헤드)로 ticker별 **정확 2점**(`close*adj_factor` DECIMAL 곱)만 추출(18k 행). **나눗셈(score=end/start-1)은 Python Decimal**(`rules/factors.momentum_from_endpoints`·기존 momentum 산출 재사용). 모듈경계 = SQL 추출(data)·Decimal 계산(rules).

3. **포트(옵트인)**: `PriceSeriesPort` 불변·신규 `MomentumScorePort`(옵트인)·`DuckDBPriceSeriesPort`·`engine._rank_at` isinstance 분기(Fake/Parquet 폴백 보존).

## 대안 (Alternatives) — 기각

- **완전 SQL momentum**(나눗셈도 SQL): DuckDB `DECIMAL/DECIMAL` 이 **DOUBLE 승격→float 오차**. Python Decimal 과 **6/9 MISMATCH**(PoC). 수정주가/정밀도 BLOCKING 위배 → **기각**(부분 푸시다운으로 회피·6/6 bit-identical).
- **단일 consolidated Parquet**(`COPY ... TO 1파일`·DuckDB 없이): glob 회피 효과는 비슷할 수 → **Task1 EXPLAIN 측정으로 .duckdb table 과 비교 후 결정**(둘 다 컬럼 스캔·.duckdb 가 SQL 집계·재사용 편의 우위면 채택).
- **Parquet ticker 재파티션**(`exchange=/ticker=`): ticker 프루닝 가능하나 50k 디렉토리·파일시스템 부담·전량 재적재 → 기각.
- **vectorbt 등 외부 백테스트 프레임워크**: ADR-004 float 정밀도 이유로 자체구현 채택 유지 → 기각.
- **현행 유지**: 라이브 수시간(비현실) → 기각.

## 결과 (Consequences)

- **얻음**: 라이브 백테스트 실용(PoC momentum 집계 1.2초/리밸·**Parquet baseline 대비 ≥10×** 목표)·결과 bit-identical(Python Decimal 나눗셈)·기존 rules/momentum 재사용·폴백 안전.
- **감수**: 파생 저장소 1개 추가(`.duckdb`·재생성)·빌드 ~47초(1회·bulk finalize 동반)·디스크 2.64GB. 빌드 중 동시성 = `bulk --finalize` 격리 실행(상주 app 정지·CLAUDE.md 벌크 규약).
- **재검토 트리거**: 다년 전체 적재 증가 시 인덱스 성능·디스크·증분 갱신(현 전량 재생성).
- ⚠️ **`meta.validated=false` 불변**: 이 작업은 속도 실용화·룰 검증 아님. validated=true 는 S6-b 신뢰성 게이트(분할≥10·커버리지·민감도) 통과 후(별개).
