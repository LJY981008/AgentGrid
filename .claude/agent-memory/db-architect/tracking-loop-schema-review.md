---
name: tracking-loop-schema-review
description: 추적·보정 루프(portfolio_round·trade) 스키마 검토 판정(REVISE-GO)과 실측 근거 — SPY 부재 확정·이월×SELL검증 모순·분할/배당 혼입 (2026-07-07)
metadata:
  type: project
---

추적·보정 루프(alembic 0004 예정) 데이터 모델 검토 결과 (2026-07-07, REVISE-GO).

**Why:** validated 룰 0개 상태에서 운용 규율·실측 피드백 축 착수. 사용자 비준 결정(라운드 단위·수동 거래입력·SPY+Top20 벤치·구조화 회고)은 유지하되 스키마 모순 5건 발견.

**How to apply:** 0004 마이그레이션 설계 시 아래 blocking 반영. 실측 근거는 재검증 없이 인용 가능(단 SPY 는 수집 후 stale).

## 실측 확정 사실
- **SPY 데이터 없음**: `stockpick_parquet-data` volume `/data/parquet/daily_bar/exchange=*/year=*/` 전수 탐색 — SPY.parquet 부재(SPYR·SPYUF 만 존재, 무관 종목). stock 마스터는 Common Stock 전용(db.py master_tickers docstring). SPY(ETF) 추가 시 stock_snapshot.json→MasterUniverse 로 흘러 **백테스트 유니버스 오염** 경로 존재 → security_type 컬럼으로 차단 필요.
- adj_factor(types.py) = 누적조정계수, adjusted=raw*adj_factor. Tiingo adjClose·EODHD adjusted_close 모두 **분할+배당 혼합** — split-only factor 아님.
- Parquet 파티션 실측: `daily_bar/exchange=X/year=Y/{TICKER}.parquet` (hive 2단 + 파일명 ticker).
- 기존 관행: raw SQL op.execute·CHECK(0002 listing_status 패턴, 새 ENUM 지양)·docstring 헤더·downgrade 대칭·FK 미강제는 시장데이터(daily_bar D2)만 — 운용기록 소량 테이블은 강제 FK 무방.

## Blocking 5건 요약
1. 보유 이월 × trade.round_id 귀속 × SELL>보유 검증 × close 불변 — 상호 모순. 포지션 원장은 stock 단위 전역 누적, round_id 는 귀속 라벨, round open 시 carry-in 스냅샷.
2. 분할 시 수량 모델 부재 + adj_factor 비율은 배당 혼입(실보유 평가 왜곡). corporate_action(split-only factor, EODHD splits) 1급 필요.
3. SPY 부재+유니버스 오염(위 실측).
4. trade.ticker 문자열 단독 → 보유 중 티커 변경 시 조용한 stale 가격. stock_id FK + ticker(입력 사실) 병기, 평가는 ticker_history 해소.
5. 정정 경로 부재 — soft-void(voided_at·void_reason) append-only, 물리 DELETE/UPDATE 금지.

## JSONB vs 정규화 판정
- top20_snapshot=JSONB(불변 시점캡처) + rule_signature·validated 컬럼 승격 / top5=정규화(round_pick 테이블, 조인 앵커) / performance_snapshot=JSONB(동결 파생) + 내부에 계산명세(가격기준일·anchor·코드버전) 필수.
- **PG 1차 진실 예외**: round/trade 는 Parquet 원본 없는 PG 유일본 — db.py 헤더의 "PG=파생·직접수정 금지" 원칙을 시장데이터 테이블로 스코프 한정 + pg_dump 백업 필요.

[[s5a-pg-schema-design]] [[m1-storage-schema]]
