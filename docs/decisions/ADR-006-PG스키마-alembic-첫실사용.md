# ADR-006: PG18 코어 스키마 + alembic 첫 실사용 (S5-a)

- **날짜**: 2026-06-18
- **상태**: 승인
- **결정자**: 사용자 / Claude 협의 (brainstorming + critic 적대적 리뷰)
- **관련**: [[ADR-001-마이그레이션-도구-alembic]](채택 결정 — 본 ADR 이 첫 실사용)·[[plans/M1-데이터파이프라인]] §3 스키마·§7 D2/D3/D5·설계 스펙 `docs/superpowers/specs/2026-06-18-S5a-적재안전성-설계.md`

## 맥락 (Context)

EODHD 결제 완료 → S5(다년·전체유니버스·폐지 포함 적재) 잠금 해제. S5 를 4분해(a→b→c→d). S5-a(적재 안전성)에서 종목마스터를 **PG/alembic 로 저장**(JSON 아님 — 사용자 결정)하기로 했고, 첫 마이그레이션에 `stock`+`ticker_history`+`daily_bar` 를 **전부** 넣기로 했다(사용자 결정). ADR-001 이 alembic 을 채택했으나 미사용 상태였고, 이게 첫 실사용이다. 스키마는 생존편향·룩어헤드(돈 걸림)를 1급으로 반영해야 한다.

## 결정 (Decision)

**alembic + psycopg3 로 PG18 코어 3테이블을 단일 첫 마이그레이션으로 생성한다.**

1. **alembic 첫 실사용**: `migrations/`(src 밖·인프라)·`env.py` 가 compose `DATABASE_URL`(`postgresql://`→`postgresql+psycopg://` 치환) 읽음·`target_metadata=None`(ORM 모델 없음, PG18 기능은 raw SQL `op.execute`). 드라이버 = **psycopg3**(`psycopg[binary]`). SQLAlchemy 는 alembic 전이의존. ⚠️ 버전은 `uv add` 후 uv.lock 실측 고정(ADR-001 — 추측 금지). 실측 버전: alembic·SQLAlchemy·psycopg = (Task2 적재 시 기입).

2. **R1 — stock PK = surrogate BIGINT + cik nullable UNIQUE**: cik 를 PK 로 강제하면 cik 미해소(EODHD CIK 미제공·EDGAR 현재스냅샷만 → 폐지·ETF·외국주 다수)가 적재 불가 → 생존편향 누수(BLOCKING). 인공 `id BIGINT GENERATED ALWAYS AS IDENTITY` PK + `cik` nullable, 부분 UNIQUE(`WHERE cik IS NOT NULL`).

3. **⚠️ cik `""` ≡ 미해소 ≡ NULL (repo 경계 매핑)**: 코드베이스는 cik 를 `""`(빈 문자열)로 폴백한다(`eodhd.py:243`·`edgar.py`·`types.py:49 cik: str`) — 절대 None 아님. PG 부분 UNIQUE(`WHERE cik IS NOT NULL`)는 `""` 를 non-null 로 취급해 **미해소 2번째 종목에서 충돌**한다. 따라서 **repo(`upsert_stocks`)가 적재 직전 `cik == ""` → SQL NULL 로 매핑**한다(`types.Stock.cik: str` 도메인 계약은 불변 — 경계 변환만). 미해소 다수가 NULL 로 공존(생존편향 누수 0).

4. **upsert 메타 = repo 파라미터**: `stock.source`·`ingested_at`(NOT NULL)는 `types.Stock` 에 없으므로 `upsert_stocks(stocks, *, source, ingested_at)` 파라미터로 받는다(`write_daily_bars` 의 source/ingested_at 계약 미러). types.Stock 에 추가 안 함(도메인 계약 변경 회피).

5. **D2 (FK)**: `daily_bar → stock` 직접 FK **안 함**. ticker 는 시변·N:1(재사용)이고 벌크 COPY 성능·1인 운영이라 FK 강제는 부담. 고아 ticker 는 사후검증 쿼리로 탐지.

6. **D3 (파티션)**: `daily_bar PARTITION BY RANGE(trade_date)` 연도별 수동(pg_partman 미사용·1인) + DEFAULT 파티션 안전망. PK(ticker, trade_date) — 파티션 키 포함(PG 요건).

7. **D5 (Parquet↔PG 동기)**: **단방향 Parquet(1차 진실원본)→PG(파생 서빙)**. `INSERT ... ON CONFLICT(ticker,trade_date) DO UPDATE` 멱등(⚠️ COPY 아님 — COPY 는 ON CONFLICT 미지원). PG 직접 수정 금지(역류=오염). S5-a 는 동기 **함수**까지, 전체 벌크 동기 실행은 S5-c.

8. **dedup 신규우선 (G1)**: Parquet write read-merge-write 시 같은 (ticker, trade_date) 충돌은 **신규 값 우선**(adj_factor 정정 반영). `build_expected` 는 행수만 봐 값 교체를 못 잡으므로 value-replacement 테스트로 봉인.

## 검토한 대안 (Alternatives)

| 대안 | 판정 | 사유 |
|---|---|---|
| stock PK = surrogate + cik nullable UNIQUE (채택) | ✅ | cik 미해소 폐지·ETF·외국주 적재 → 생존편향 누수 0 |
| stock PK = cik NOT NULL | ❌ | cik 미해소 종목 적재 불가 → 생존편향 누수(BLOCKING 위반) |
| 종목마스터 = Parquet/JSON(PG 미도입) | ❌(사용자 PG 선택) | 기존 패턴엔 맞으나 사용자가 PG/alembic·daily_bar 까지 PG 결정 |
| daily_bar↔stock FK 강제 | ❌ | ticker 시변 N:1·벌크 성능·1인 — 사후검증으로 대체 |
| Parquet↔PG 양방향 | ❌ | PG 역류 = 1차 진실원본 오염. 단방향만 |

## 결과 (Consequences)

- **얻는 것**: 생존편향-correct 종목마스터 기반(폐지·미해소 포함)·운영 서빙 PG·alembic 마이그레이션 재현성·다년 증분 소실 봉인(G1)·CHECK 2차 방어선(PG=DuckDB 게이트 동형).
- **감수하는 것**: PG 인프라 의존(compose postgres·CI postgres 서비스)·daily_bar 거대 테이블 파티션 운영·Parquet↔PG 동기 지연(일1회 배치).
- **재검토 트리거**: daily_bar 파티션 수동 관리 부담 급증 시 pg_partman / 동기 지연이 문제면 증분 동기 빈도 / cik 매핑 정확도(ticker_history 시점 해소는 S5-b+).

## 관련

- [[ADR-001-마이그레이션-도구-alembic]] · [[plans/M1-데이터파이프라인]] · [[../work-history/2026-06-18-S5a-적재안전성]] · 스펙 보정: 본 ADR 이 설계 스펙 §3.1(source/ingested_at=repo 파라미터)·§3.4(redact 불요 — level WARNING+어댑터 URL 미로깅 충분)·§3.5(COPY→INSERT ON CONFLICT) 를 정정한다.
