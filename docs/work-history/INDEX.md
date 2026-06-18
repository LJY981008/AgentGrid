# 구현 히스토리 인덱스

> 모든 구현 작업(플랜모드/일반 불문)의 의도·계획·전후 비교 기록.
> 규약: 코드(src) 변경 커밋에는 이 디렉토리의 엔트리가 동반되어야 함 — harness-drift-check 가 물리 강제.
> 새 엔트리: `docs/templates/work-history-template.md` 복사 → `{YYYY-MM-DD}-{작업명}.md` → 아래 표에 행 추가.

| 날짜 | 작업 | 유형 | 엔트리 |
|---|---|---|---|
| 2026-06-12 | work-history 체계 도입 | 하네스/인프라 | [[2026-06-12-work-history-체계-도입]] |
| 2026-06-12 | 프론트 목업 4화면 (와이어프레임 대용) | 일반 구현 | [[2026-06-12-프론트-목업-4화면]] |
| 2026-06-16 | M0 — 도메인·스택 전환 (MCP→한국주식, Java/Next→Python/PWA) | 하네스/인프라 | [[2026-06-16-M0-스택전환]] |
| 2026-06-16 | M1 S0-S1 — 결정 확정·계약 정밀도 교정(float→Decimal) | 일반 구현 | [[2026-06-16-M1-S0S1-결정·계약교정]] |
| 2026-06-16 | B-env — Docker 기반 uv 개발/실행 환경(Dockerfile·app 서비스·uv.lock) | 하네스/인프라 | [[2026-06-16-B-env-docker-uv]] |
| 2026-06-16 | B-contract — 미국 도메인 계약 재설계(CIK+ticker·Exchange·DataSource Protocol) | 일반 구현 | [[2026-06-16-B-contract-미국계약]] |
| 2026-06-16 | B-pipeline — Tiingo EOD 가격 어댑터(httpx·adj_factor·모킹 테스트, 라이브 0) | 일반 구현 | [[2026-06-16-B-pipeline-tiingo-어댑터]] |
| 2026-06-16 | B-pipeline — 저장층(Hive Parquet·decimal128·DuckDB 검증) + 라이브 파일럿(분할 교차검증) | 일반 구현 | [[2026-06-16-B-pipeline-storage-pilot]] |
| 2026-06-16 | TASK-B — 검증 게이트 소실 탐지(expected vs actual 대조, 생존편향 누수 봉인) | 일반 구현 | [[2026-06-16-TASK-B-게이트-소실탐지]] |
| 2026-06-16 | TASK-C/D — adj_factor quantize 공유 헬퍼(scale 37→12) + EodhdSource 어댑터(폐지 유니버스·라이브 0) | 일반 구현 | [[2026-06-16-TASK-CD-quantize-eodhd어댑터]] |
| 2026-06-16 | 코드리뷰 반영 — 양수성 게이트(음수/0 가격·adjusted 차단)·httpx 토큰 가드 코드화·테스트 타입 정리(77→89 passed) | 일반 구현 | [[2026-06-16-코드리뷰-반영]] |
| 2026-06-17 | EODHD 미니 데이터셋 적재 — 소스무관 generic 적재기(ingest.py)·누적검증 소실탐지·라이브 9종목 2259행 PASS | 일반 구현 | [[2026-06-17-EODHD-미니데이터셋-적재]] |
| 2026-06-17 | M2 (c) 룰엔진 수직 슬라이스 — 모멘텀 팩터(수정주가·룩어헤드 2중 가드)→Top 랭킹(TopEntry). 라이브 데모·sabotage 검증·테스트 18(114 passed) | 일반 구현 | [[2026-06-17-M2-룰엔진-수직슬라이스]] |
| 2026-06-17 | webapp PWA 대시보드 + API 층(M3) — FastAPI(수집·랭킹·학습) + Vite+React+TS PWA(랭킹·데이터·유니버스·학습·백테스트 placeholder) | 플랜모드 승인 | [[2026-06-17-webapp-API-대시보드]] |
| 2026-06-17 | M3 A층 — FastAPI API(health·dataset·ingest·ranking·learning, pydantic 계약·CORS·키비노출·path-traversal 가드). 테스트 20(134 passed)·기동 스모크 wire-shape 캡처 | 일반 구현 | [[2026-06-17-API-층-FastAPI]] |
| 2026-06-17 | M3 B층 — webapp PWA 프론트 전체(Vite8/React19/router7 5화면·미검증 경고 상시·urlTransform·SW). node:22 build·tsc strict 통과(296 모듈) | 일반 구현 | [[2026-06-17-webapp-프론트]] |
| 2026-06-17 | 하네스·docs 전수 감사 + 최신화 — 9차원 병렬 감사(26에이전트)·적대적 검증. 도메인 잔재(한국→미국)·마일스톤 stale·MOC 누락·죽은 drift 매핑·SHA 백필 28파일 교정(134 passed·훅 38) | 하네스/인프라 | [[2026-06-17-하네스docs-전수감사-최신화]] |
| 2026-06-17 | M2 백테스트 엔진 골격 — 자체구현(ADR-004) backtest/ 14모듈: 리밸·forward-return·폐지청산·CAGR/Sharpe/MDD·IS/OOS·decay·등가중벤치. 적대적 금융리뷰 2회 반영. 173 passed·데모 9종목 동작 | 플랜모드 승인 | [[2026-06-17-M2-백테스트엔진]] |
| 2026-06-17 | 백테스트 API 노출 + webapp BacktestPage 교체(#4) — GET /api/backtest + 프론트 자산곡선(Recharts)·지표·벤치·미검증경고. PriceDerivedUniverse 신설(demo smell 제거) | 플랜모드 승인 | [[2026-06-17-백테스트-API-webapp]] |
| 2026-06-17 | EDGAR cik resolver(#2) — SEC company_tickers.json(무료·키없음·User-Agent) 적재→저장→읽기. EdgarSnapshotResolver(IdentityResolver 실전)·Stub 교체·ranking/backtest cik enrich. 현재 스냅샷(ticker_history 후속) | 플랜모드 승인 | [[2026-06-17-EDGAR-cik-resolver]] |
| 2026-06-17 | 백테스트 리밸 루프 공유 헬퍼(#5 리팩터) — engine/benchmark 복제 루프를 calendar.holding_periods(회계 경계 단일출처)로 추출. 동작 불변(197 passed). 드리프트 리스크 제거 | 리팩터 | [[2026-06-17-백테스트-루프-공유헬퍼]] |
| 2026-06-18 | EDGAR 재무층 슬라이스(#재무-1) — companyfacts 직접파싱(소수 concept)·FinancialFact·PIT(filed<=t)·ROE/P/B 팩터→ranking factors 노출(결합 안함·§9-2). edgartools 미사용(ADR-005). SEC 무료·결제 무관 | 플랜모드 승인 | [[2026-06-18-EDGAR-재무층]] |
| 2026-06-18 | S5-a 적재 안전성 선결 — PG 코어 스키마(alembic 첫 실사용·stock+ticker_history+daily_bar·surrogate PK·cik""≡NULL)·G1 write read-merge-write(소실 봉인)·data/db.py(Parquet→PG 단방향 동기). EODHD 결제 후 S5 4분해 첫 단계(ADR-006) | 플랜모드 승인 | [[2026-06-18-S5a-적재안전성]] |
| 2026-06-18 | S5-c 벌크 가격 적재 — 종목마스터 50,184 대상 다년 EOD→Parquet(백테스트 진실원본)·체크포인트/재시도·verify 1회(O(n²) 회피)·stock 날짜 backfill·커버리지 요약. Parquet 벌크만(PG 동기 이연)·풀런 운영자 트리거. critic 1C+4M 반영 | 플랜모드 승인 | [[2026-06-18-S5c-벌크가격]] |
| 2026-06-18 | S5-b 종목마스터 채움 — EODHD Common Stock 유니버스(폐지 포함)→PG stock UPSERT(listing_status·cik EDGAR enrich)·ticker_history 현재 스냅샷·G2 master_tickers. 날짜는 S5-c·거래소 OTC 한계. critic 2회 반영(C1 클라필터1차·C2 EXCLUDE S5-d·B1 resolved/unresolved 분리) | 플랜모드 승인 | [[2026-06-18-S5b-종목마스터]] |
