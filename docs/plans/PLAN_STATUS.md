# 기획 문서 현황

> 🔄 **작업 재개(compact 생존)**: 진행상황·다음 작업·환경·함정은 **[작업재개-RESUME](작업재개-RESUME.md)** 하나로. compact된 세션은 이거부터 읽고 이어가라.
> 최근(2026-06-23 ②): **S6-b 신뢰성 게이트 구축 + 전구간 풀 실행 → 판정 `validated=false`**(ADR-009·Task0~5). `backtest/s6_gate.py`(G-1~G-8 **사전동결** 임계 모듈상수·`run_s6_gate`·`sensitivity_analysis` 비용민감도·`evaluate_criteria` 순수판정·`compute_rule_signature`/`load_s6_gate_verdict` **validated flip**·격리 CLI). ranking/backtest `meta.validated` 하드코딩→flip 배선. Task별 리뷰 2종. **풀 실행 판정: G-7 무결성 FAIL**(가격<=0 **542,588행**·OHLC위반 **88,064행** — **99.6% 비-`_old` 일반티커**·원인 미상[`_old` 0.39%뿐]·verify 정확). 데이터 신뢰 불가 → momentum OOS 강건성 **미평가**(G-7 단락·garbage-in 방지)·validated=false **유지가 정답**(정직 판정). **2개 실버그 발굴·수정**: ① `verify_parquet` DuckDB memory_limit 미설정 OOM(cgroup 무인지·`_VERIFY_MEMORY_LIMIT` 4GB+spill) ② 백테스트 단계 12g OOM(백로그·데이터정제 후 mem>12g). 8hr 추정→G-7 단락으로 ~4min 종결. **다음=데이터 정제(0-price 행)→게이트 재실행(mem>12g)→momentum G-1~G-6 실판정.** 상세=RESUME.
> 최근(2026-06-23): **벤치 멤버십 SQL 푸시다운 + 관측성 스택(Prometheus+Grafana·ADR-008)**. ① 벤치 `equal_weight_universe`가 매 리밸 `load_range(18k×window)`로 3.65M PricePoint를 멤버십 판정에만 물질화(병목) → `tickers_with_data`(DISTINCT·NULL 가드·키집합 동치) → 풀 백테스트 **70→25.5분(2.7×)**·결과 bit-identical·리뷰 2종 APPROVE(`fc4fbc6`/`8d54025`). ② 측정 임시방편(time.monotonic·ru_maxrss)·peak 11.7GB 원천 미확정 → **관측성 스택**: `PhaseProfile` 계측(stdlib·결과불변 BLOCKING)·profile CLI(라이브 /metrics·**rss vs python peak 범인 가림**·Pushgateway round)·instrumentator·compose 4서비스(prometheus v3.12.0·grafana 13.0.2[3001]·pushgateway·profiler)·**레이어 대시보드**(L1 신호등/L3 파이프라인/L4 무결성/호스트·tbbe-hub 모델)·Local Snapshot. Task1~6·라이브 scrape 검증. **`meta.validated=false` 불변**(관측성=속도/메모리 최적화). **다음=peak 범인 확정 후 메모리 최적화→S6-b 게이트.** 상세=RESUME.
> 최근(2026-06-22 ②): **S6-a full_series OOM 수정 + 백테스트 라이브 실용화(DuckDB 컬럼스토어+momentum 부분 푸시다운·ADR-007)**. S6-a — engine/벤치 `full_series`(5.1G 전체메모리 OOM)→`load_range`(종목×윈도우). 후속 — `data/duckdb_cache.py`(Parquet→`cache.duckdb` 단일 컬럼 table·1억49만행·1.29GB·인덱스 없음[SEQ_SCAN]) + **momentum 부분 푸시다운**(`momentum_endpoints` SQL 끝점 2점·`close*adj_factor` DECIMAL 곱·**나눗셈만 Python Decimal**[SQL float 승격 회피]·`momentum_from_endpoints`) + `DuckDBPriceSeriesPort`(`MomentumScorePort`)·`_select_price_port`(폴백)·engine `isinstance` 분기. Task0~7·Task별 리뷰 2종(Task2 결과불변 BLOCKING 버그 tot→wn 조기 차단). 측정: **단일 리밸 ranking 43.3s→1.34s=32.3×**(≥10×)·실데이터 18,311종목 **score 불일치 0**(bit-identical). 풀 백테스트 774리밸 **완주**(70분·peak 12,033MB·OOM 0). ⚠️ **풀 wall-clock ≥10× 미달** — 병목이 ranking→**벤치 `equal_weight_universe` 멤버십 load_range**(3.65M PricePoint/리밸·benchmark.py:64)로 이동(finding). **`meta.validated=false` 불변**(속도 실용화·검증 아님). **다음=벤치 멤버십 SQL 푸시다운(풀 백테스트 실용화 선결)→S6-b 게이트→validated=true**. 상세=RESUME.
> 최근(2026-06-22): **풀백필 완주(50,184·5.1G) + S5-c 후처리 버그수정 + S5-d 실 UniversePort 완료**. EODHD $19.99 결제(06-18)·S5-a/b/c 후 전체 풀백필(OOM 1회→app `mem_limit:12g` 격리 복구·완주). 발견·수정: run_bulk 후처리(`verify_parquet` ≥400s)가 `update_stock_dates`·commit 막아 PG 날짜 **29/50,184만** → 후처리 재구조화(commit 호출부·C1·verify `--verify` 옵션화)·**`--finalize` 복구**(날짜·snapshot **50,184**)·**`MasterUniverse`**(delisted_at+1 경계·생존편향 유니버스·`_select_universe` 배선). critic REVISE 2C+3M·Task별 리뷰 2종. ⚠️ **라이브 `/api/backtest` 풀 산출은 `full_series`(5.1G 전체메모리) OOM** → **다음=S6**(full_series DuckDB 집계 수정 **선결**·신뢰성 게이트→`validated=true`)·증분 스케줄러. 상세=RESUME "📍 다음 작업 순서".
> 최근(2026-06-17): **M2 룰 수직슬라이스 + M3 API/webapp 완료**. M2 — EODHD generic 적재(무료 1년치 9종목, history 무관 설계)·룰엔진 수직슬라이스(rules/ 모멘텀→Top 랭킹, 룩어헤드 sabotage 검증, 114 passed, ec9d3b0). M3 — FastAPI API층(src/stockpick/api/ 수집·랭킹·학습 HTTP 노출, 2c9ab10) + webapp PWA 5화면(webapp/ Vite/React, b7c5b21). **M2 백테스트 엔진 골격 완료**(backtest/ 14모듈: 리밸·forward-return·폐지청산·CAGR/Sharpe/MDD·IS/OOS·decay·등가중벤치·자체구현 ADR-004, 173 passed, 골격 데모 9종목 13기간 동작·룰이 등가중벤치 언더퍼폼=미검증 입증). **다음=S6 데이터 신뢰성 게이트**(EODHD 결제 다년·전체유니버스·실폐지·cik 매핑) 통과 후 룰 검증. | (06-16): **TASK-A~D + 전체점검 완료** — 도커컴포즈 라이브 파일럿 통과·다차원 코드리뷰(BLOCKING 0·M2 가능)·리뷰반영(양수성 게이트·httpx 가드·89 passed, 7f3b286). **TASK-A~D 완료** — EODHD 명세(`docs/apis/eodhd/` 62섹션)·게이트 소실탐지(734a52f)·adj_factor quantize·EodhdSource 어댑터(42df8d1, 모킹 77 passed). **다음 = TASK-E(S5 전체 유니버스) — EODHD 결제 후 라이브**. ⛔라이브 전: httpx 토큰누출 가드(`httpx 로거 WARNING`).

> 기획 문서 추가/수정 시 이 표를 같은 커밋에서 갱신한다 (harness-drift-check 가 감지).
> 기획 문서는 버전 넘버링으로 추가 — 기존 파일 덮어쓰기 금지.

## ⚠️ 도메인 전환 (2026-06-16)

이 레포는 **MCP 신뢰성 레지스트리 → 개인 투자용 주식 주가 분석 프로그램**으로 전면 전환됐다 (사용자 확정). 레포 골격(하네스·git·볼트·work-history 규약)은 유지, 스택은 Java/Spring+Next → **Python 서버 + PWA 웹앱** 으로 교체. 현행 기준선 = `stock-1st_plan.md`.

### ⚠️ 시장 전환 (2026-06-16, 같은 날 후속): 한국 → **미국 주력**

분석 대상 시장을 **미국 주식(NYSE/NASDAQ/AMEX)**으로 전환(사용자 결정). 사유: 사용자 학습·관심이 미장 중심(SEC/FED). 데이터 아키텍처 = [ADR-002](../decisions/ADR-002-미국-데이터소스-아키텍처.md) + [미국 데이터소스 리서치](../research/2026-06-16-미국주식-데이터소스.md). 시장 무관 자산(BLOCKING 원칙·`types.py` Decimal·파이프라인 철학·M1 스키마 PIT 설계)은 그대로 유효 — financial `disclosed_at` 설계가 EDGAR `filed`와 1:1로 오히려 더 잘 맞음. 한국 데이터소스/KRX 키는 보류(나중 한국장 추가 시 재사용).

| 문서 | 상태 | 요약 |
|---|---|---|
| [stock-1st_plan.md](stock-1st_plan.md) | **현행 기준선 (baseline)** | 한국주식 분석: 확정 결정 5건(in-place 전환·Python+PWA·Top20정량→수동Top5→분산투자추적·보정·AI자동화 보류·1인용), Top20 7팩터 후보, 백테스트 BLOCKING 원칙, MVP 마일스톤 M0~M4, 미해결 질문 8건 |
| [M1-데이터파이프라인.md](M1-데이터파이프라인.md) | **현행 (M1 착수 스펙)** | 실측 스코핑 종합: 소스(FDR 0.9.202+pykrx 1.2.8/KRX OpenAPI)·PG18 7테이블 스키마·파일럿 S0~S6 순서·BLOCKING 가드. 결정=[ADR-001](../decisions/ADR-001-마이그레이션-도구-alembic.md) |
| ~~1st_plan.md~~ | 폐기 (도메인 전환) | (구) MCP 비전·기술스택 — 보존만, 무효 |
| ~~2nd_plan.md~~ | 폐기 (도메인 전환) | (구) 신뢰성 지표 6축·MVP 명세 — 보존만, 무효 |
| ~~3rd_plan.md~~ | 폐기 (도메인 전환) | (구) 미해결 질문 5건 확정 — 보존만, 무효 |

## 데이터 소스 리서치 (~~한국 — 보류~~, 미장 전환)

> ⚠️ **현행 = 미국**: 가격 Tiingo(파일럿)→**EODHD**(M2, ADR-003·폐지 ~2000년부터·raw+adjusted) / 재무 **SEC EDGAR**(filed=PIT)+edgartools / 저장 Parquet+DuckDB+PG18(불변). 상세 [미국 데이터소스 research](../research/2026-06-16-미국주식-데이터소스.md). 리스크: 미국 무료티어엔 폐지 가격 없음(유료 EODHD 필수)·생존편향(폐지 포함 유니버스)·adjusted_close 정의 통일·CIK↔ticker 재사용 누수.
> 아래 한국(FDR/pykrx/KRX) 서술은 **2026-06-16 미장 전환으로 보류** — 나중 한국장 추가 시 재사용 ([한국 research 노트](../research/2026-06-16-한국주식-데이터소스.md)).

- **(A) 30년 벌크 백테스트** = FinanceDataReader(KRX 1995~, **폐지종목 KRX-DELISTING** 별도) + pykrx(재무·시총·거래대금 보강)
- **(B) 일일 증분 갱신** = KRX OpenAPI(공식·안정, 단 2010~) 우선 / pykrx 차선
- **저장** = Parquet+DuckDB(백테스트 스캔) + PostgreSQL 18(운영 서빙). **TimescaleDB 는 일봉에 과투자 → 현 단계 비권장**
- 핵심 리스크: 공식 단독 30년 불가(비공식 의존 불가피) / 생존편향(폐지종목 필수) / 수정주가 정의 통일 / 비공식 차단

## 미해결 질문 (stock-1st_plan §9 — 사용자/조사 결정 필요)

| # | 질문 | 우선순위 | 상태 |
|---|---|---|---|
| 1 | 데이터 소스 확정 (리서치 추천안 채택 여부) | M1 선결 | ✅ **해결(미국)** — 가격 Tiingo(파일럿)→**EODHD**(본격 M2, [ADR-003](../decisions/ADR-003-M2-가격소스-EODHD.md)이 ADR-002의 Sharadar SEP를 개정) / 재무 SEC EDGAR+edgartools ([ADR-002](../decisions/ADR-002-미국-데이터소스-아키텍처.md)) |
| 2 | Top20 룰 팩터·가중치 (백테스트로 결정) | M2 | 이월 |
| 3 | 백테스트 프레임워크 (vectorbt/backtrader/자체) | M2 | 이월 |
| 4 | 시계열 DB 선택 (PG vs Parquet vs 혼용) — db-architect | M1 선결 | ✅ **해결** — Parquet(1차)+PG18(서빙), TimescaleDB 비채택 |
| 5 | 분산투자 비중 산정 방식 | M3 | 이월 |
| 6 | 데이터 갱신·룰 재평가 주기 | M3 | 이월 (Parquet↔PG 동기와 연동) |
| 7 | 거래비용·세금 모델링 | M2 | 이월 |
| 8 | 폐지종목 확보 불가 시 fallback | M1 | ✅ **해결** — 확보분 전량+누락 정량 고지, 커버리지 하한 미달 시 M1 차단 |

**추가 확정 결정 (2026-06-16)**:
- **마이그레이션 도구** = alembic ([ADR-001](../decisions/ADR-001-마이그레이션-도구-alembic.md))
- **미국 데이터 아키텍처** = [ADR-002](../decisions/ADR-002-미국-데이터소스-아키텍처.md): 가격 Tiingo(파일럿)→**EODHD**(M2, [ADR-003](../decisions/ADR-003-M2-가격소스-EODHD.md) — 가성비 1위 $19.99/월·raw+adjusted·폐지 2000~) / 재무 EDGAR(filed=PIT)+edgartools / 결합 `merge_asof`. **SimFin 기각**(PIT 미충족) · **RabbitMQ·LLM 런타임 정규화 기각**. history: 30년 강제 아님(예시) → 데이터 가용범위 전부(많을수록 검증 정확도↑). 유료 해지-삭제 조항은 재현성과 무관(과거 EOD 불변·재구독 재취득)
- **수정주가 통일** = Tiingo adjClose/EODHD adjusted_close 기준, 원주가+adj_factor 분리, 분할표본 교차검증
- **데이터 신뢰성 게이트** = M1은 넓게 수집 + 종목·기간별 품질 꼬리표 저장(단일 임계로 파기 안 함). 표준(1%)·엄격(0.5%) 임계는 **M2 백테스트 민감도 분석**(두 시나리오 gap = 강건성 진단, gap으로 임계 골라잡기=과적합 금지)

**진행 현황**: M0 ✅ → M1 S0·S1 ✅(결정·ADR·계약 Decimal) → 미장 전환·ADR-002/003 ✅ → **B-env·B-contract·B-pipeline** ✅(Docker+uv·types.py 미국 재설계·Tiingo 어댑터·라이브 파일럿 0f69a53) → **EODHD 어댑터** ✅(TASK-A~D 코드층 42df8d1) → **EODHD 무료 1년치 9종목 적재** ✅(ingest.py 2259행 b154bff) → **M2 룰엔진 수직슬라이스** ✅(rules/ 모멘텀 팩터→Top 랭킹·룩어헤드 sabotage 검증·114 passed ec9d3b0) → **M3 API+webapp** ✅(FastAPI api/ HTTP 노출 2c9ab10 + webapp/ PWA 5화면 b7c5b21) → **M2 백테스트 엔진 골격** ✅(backtest/ 14모듈·자체구현 ADR-004·금융가드 sabotage·173 passed). **EDGAR 재무층 슬라이스** ✅(#재무-1, 2026-06-18 — companyfacts 직접파싱 ADR-005·FinancialFact PIT(filed)·ROE/P/B 팩터→ranking factors 노출·라이브 9종목 4571 fact·231 passed). 미완: S6 데이터 신뢰성 게이트(EODHD 결제 후 전체 유니버스·실폐지·cik)·재무 커버리지 확장(변형태그·다중클래스 주식수·TTM·edgartools).

> ⚠️ **마일스톤 번호 정합**: 커밋이 부르는 M3(FastAPI API+webapp PWA)는 베이스라인 [stock-1st_plan](stock-1st_plan.md) §8의 **M4(웹앱 뷰)+신규 API층**에 해당. 베이스라인 M2의 **백테스트 절반**(랭킹만 구현, backtest/ 빈 패키지)과 베이스라인 M3(**Top5 수동 워크플로·보유추적·룰버전이력**)는 **미구현**(추적 루프는 데이터/룰 안정화 후). 향후 마일스톤은 §8 번호로 통일하거나 §8을 현 실제순서로 개정 — 결정은 product-planner 위임 권장.

**다음 단계**: **S5 다년·전체유니버스 적재 → S6 신뢰성 게이트 → 백테스트 실검증**. ✅ **EODHD 결제 완료(2026-06-18 · EOD Historical $19.99)** — 능력 목록 [docs/apis/eodhd/pricing_plan/PLANS.md](../apis/eodhd/pricing_plan/PLANS.md)(가격·수정주가·폐지·분할배당·30년+ ✅ / 재무 ❌→EDGAR). 완료: 백테스트 엔진 골격(`backtest/` 14모듈)·#4 `/api/backtest`+webapp BacktestPage(Recharts)·#2 EDGAR cik resolver(라이브 10,414건)·#5 리밸 루프 공유헬퍼·#재무-1 EDGAR 재무층(ROE/P/B). 선결(S5 = 4분해 a→b→c→d): **S5-a**(적재 안전성·PG 스키마·alembic·ADR-006·G1·`data/db.py`)·**S5-b**(종목마스터 채움·`data/universe.py`·EODHD Common Stock 50,184 security·listing_status·cik enrich·다중클래스주 보존 (cik,ticker) UNIQUE·migration 0003·246 passed) **완료**(2026-06-18). **S5-c**(벌크 가격 적재·`data/bulk.py`·체크포인트/재시도·verify 1회·날짜 backfill·커버리지·Parquet 벌크만 PG 동기 이연·스모크 `--limit 20` PASS·259 passed·전체 50,184 풀런=운영자 트리거 수시간) **완료**(2026-06-18). 미완: ①전체 풀런(운영자) ②S5-d 실 UniversePort(G7·`PriceDerivedUniverse` 교체)·ticker_history EXCLUDE·시점 cik(`TickerHistoryResolver`)·거래소 정밀화·S6 게이트→validated=true. **그 전까지 `meta.validated=true` 금지**(§4.1 BLOCKING — 결제만으로 검증 아님, 다년 데이터+게이트 필요). **전체 후속 백로그(영속 todo) = [작업재개-RESUME](작업재개-RESUME.md) §후속 백로그.**
