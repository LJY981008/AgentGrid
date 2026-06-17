# 기획 문서 현황

> 🔄 **작업 재개(compact 생존)**: 진행상황·다음 작업·환경·함정은 **[작업재개-RESUME](작업재개-RESUME.md)** 하나로. compact된 세션은 이거부터 읽고 이어가라.
> 최근(2026-06-17): **M2 룰 수직슬라이스 + M3 API/webapp 완료**. M2 — EODHD generic 적재(무료 1년치 9종목, history 무관 설계)·룰엔진 수직슬라이스(rules/ 모멘텀→Top 랭킹, 룩어헤드 sabotage 검증, 114 passed, ec9d3b0). M3 — FastAPI API층(src/stockpick/api/ 수집·랭킹·학습 HTTP 노출, 2c9ab10) + webapp PWA 5화면(webapp/ Vite/React, b7c5b21). **다음=M2 백테스트 엔진**(backtest/ 빈 패키지). | (06-16): **TASK-A~D + 전체점검 완료** — 도커컴포즈 라이브 파일럿 통과·다차원 코드리뷰(BLOCKING 0·M2 가능)·리뷰반영(양수성 게이트·httpx 가드·89 passed, 7f3b286). **TASK-A~D 완료** — EODHD 명세(`docs/apis/eodhd/` 62섹션)·게이트 소실탐지(734a52f)·adj_factor quantize·EodhdSource 어댑터(42df8d1, 모킹 77 passed). **다음 = TASK-E(S5 전체 유니버스) — EODHD 결제 후 라이브**. ⛔라이브 전: httpx 토큰누출 가드(`httpx 로거 WARNING`).

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

**진행 현황**: M0 ✅ → M1 S0·S1 ✅(결정·ADR·계약 Decimal) → 미장 전환·ADR-002/003 ✅ → **B-env·B-contract·B-pipeline** ✅(Docker+uv·types.py 미국 재설계·Tiingo 어댑터·라이브 파일럿 0f69a53) → **EODHD 어댑터** ✅(TASK-A~D 코드층 42df8d1) → **EODHD 무료 1년치 9종목 적재** ✅(ingest.py 2259행 b154bff) → **M2 룰엔진 수직슬라이스** ✅(rules/ 모멘텀 팩터→Top 랭킹·룩어헤드 sabotage 검증·114 passed ec9d3b0) → **M3 API+webapp** ✅(FastAPI api/ HTTP 노출 2c9ab10 + webapp/ PWA 5화면 b7c5b21). 미완: M2 백테스트 엔진(backtest/ 빈 패키지 38B)·EODHD 결제 후 전체 유니버스(TASK-E/S5)·EDGAR 재무층.

> ⚠️ **마일스톤 번호 정합**: 커밋이 부르는 M3(FastAPI API+webapp PWA)는 베이스라인 [stock-1st_plan](stock-1st_plan.md) §8의 **M4(웹앱 뷰)+신규 API층**에 해당. 베이스라인 M2의 **백테스트 절반**(랭킹만 구현, backtest/ 빈 패키지)과 베이스라인 M3(**Top5 수동 워크플로·보유추적·룰버전이력**)는 **미구현**(추적 루프는 데이터/룰 안정화 후). 향후 마일스톤은 §8 번호로 통일하거나 §8을 현 실제순서로 개정 — 결정은 product-planner 위임 권장.

**다음 단계**: **M2 백테스트 엔진**(`backtest/` — 현재 `__init__.py`만 있는 빈 패키지. rolling as_of·CAGR/샤프/MDD·생존편향·거래비용·룩어헤드 가드 구현). 선결: EODHD 결제($19.99/월)로 다년 history 확보 + S5 전체 유니버스(폐지 포함) 적재 + EDGAR 재무층·cik 매핑. M1 데이터 신뢰성 게이트(S6) 통과 전까지 백테스트 결과 신뢰 금지(§4.1 BLOCKING). (B-pipeline·M2 룰 수직슬라이스·M3 API/webapp은 완료.)
