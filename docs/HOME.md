# 🏠 Agent Grid 지식 베이스 (MOC)

> 옵시디언 볼트 루트. `docs/` 를 볼트로 열기. 새 문서 생성 시 [[#템플릿]] 사용 + 이 MOC 에 링크 추가
> (research/decisions 신규 문서는 harness-drift-check 가 HOME.md 동기화를 강제).

## 📋 기획 (plans/)

> ⚠️ **2026-06-16 도메인 전환**: MCP 신뢰성 레지스트리 → 개인 투자용 한국 주식 분석. 아래 1st/2nd/3rd 는 폐기(보존만).

- [[plans/stock-1st_plan|한국주식 기준선]] — **현행** Top20 정량→수동 Top5→분산투자 추적·보정, Python+PWA, 미해결 8건
- [[plans/M1-데이터파이프라인|M1 착수 스펙]] — **현행** 소스·PG18 7테이블 스키마·파일럿 S0~S6·BLOCKING 가드 (실측 스코핑 종합)
- [[plans/PLAN_STATUS|기획 현황판]] — 전환 선언 + 데이터소스 리서치 + 미해결 질문 추적(#1·#4·#8 해결)
- [[plans/작업재개-RESUME|작업 재개 가이드]] — 세션 재개(compact 생존)용 현재 상태·다음 작업·환경·함정 단일 포인터
- ~~[[plans/1st_plan]] · [[plans/2nd_plan]] · [[plans/3rd_plan]]~~ — (구) MCP 레지스트리, 폐기

## 🏛️ 아키텍처 결정 (decisions/)

> ADR 형식. 템플릿: [[templates/adr-template]]

- [[decisions/ADR-001-마이그레이션-도구-alembic|ADR-001 마이그레이션 도구 = alembic]] — 승인(2026-06-16). PG18 파티션/BRIN/ENUM 은 raw SQL 보강
- [[decisions/ADR-002-미국-데이터소스-아키텍처|ADR-002 미국 데이터소스 아키텍처]] — 승인(2026-06-16). 가격 Tiingo→(M2 EODHD) / 재무 EDGAR(filed=PIT) / SimFin·RabbitMQ·LLM정규화 기각
- [[decisions/ADR-003-M2-가격소스-EODHD|ADR-003 M2 가격소스 = EODHD]] — 승인(2026-06-16). 가성비 1위 $19.99/월·raw+adjusted 분리·폐지 2000~·Linux. ADR-002 가격 graduation 개정
- [[decisions/ADR-004-백테스트-프레임워크-자체구현|ADR-004 백테스트 프레임워크 = 자체구현]] — 승인(2026-06-17). Decimal·DuckDB 자체구현. vectorbt(float BLOCKING)·backtrader(과설계) 기각. §9-3 미결 해소
- [[decisions/ADR-005-재무-직접파싱|ADR-005 재무 정규화 = 직접 JSON 파싱]] — 승인(2026-06-18). companyfacts 소수 concept 직접 추출(ROE·P/B)·PIT(filed) 가드 직접 통제. edgartools(heavy·미검증) 미사용. ADR-002 정규화 도구 부분 개정
- [[decisions/ADR-006-PG스키마-alembic-첫실사용|ADR-006 PG 코어 스키마 + alembic 첫 실사용]] — 승인(2026-06-18). S5-a — stock(surrogate PK·cik""≡NULL 매핑)·ticker_history·daily_bar(연도 RANGE 파티션·CHECK=DuckDB 게이트 동형). 단방향 Parquet→PG(INSERT ON CONFLICT). ADR-001 첫 실사용
- [[decisions/ADR-007-백테스트-DuckDB-persistent-캐시|ADR-007 백테스트 DuckDB persistent 캐시]] — 승인(2026-06-22). Parquet→cache.duckdb 단일 컬럼 스토어(578k glob 회피)+momentum 부분 푸시다운(SQL 끝점·Python Decimal·bit-identical). 라이브 ranking 32×. 완전 SQL 나눗셈(float)·평면 Parquet 기각
- [[decisions/ADR-008-관측성-Prometheus-Grafana|ADR-008 관측성 Prometheus+Grafana]] — 승인(2026-06-23). 백테스트 phase/peak 계측(PhaseProfile stdlib·결과불변)+profile CLI(rss vs python peak 범인 가림)+Pushgateway+레이어 대시보드+Local Snapshot. Observer Protocol·라이브 동기 scrape·RSS Gauge 상시 기각
- [[decisions/ADR-009-S6b-신뢰성게이트|ADR-009 S6-b 신뢰성 게이트]] — 승인(2026-06-23). momentum 룰 검증 기준 G-1~G-8 **사전 동결**(모듈 상수·전부 AND·decay≥0.5·n_folds≥10·delisted≥30%·비용 5/10/15bps). 정직 판정 도구(fail→validated=false 유지). 데이터로 임계 고르기·CPCV·지수벤치·통과목적 튜닝 기각

## 📡 API 명세 (apis/) — 환각 방지 권위 레퍼런스

> 외부 API 실제 명세를 구조화 JSON 캡처(코드가 추측 아닌 실측 참조). 6개월 주기 재캡처.

- [[apis/README|API 명세 인덱스]] — 외부 API 권위 명세(환각 방지). 코드는 `.claude/rules/api-spec-reference.md` 로 자동 참조
  - **Tiingo**(파일럿 가격) [[apis/tiingo/_index|16섹션/34EP]] — end-of-day(raw OHLCV+adjClose+divCash), 인증 `Token` 헤더(Bearer 아님)·심볼 대시(-)
  - **EODHD**(M2 본격 가격) [[apis/eodhd/README|62섹션/189EP]] — `/api/eod/{SYM}`(raw OHLC+adjusted_close), 인증 `?api_token=` 쿼리·폐지 2000~·지수 historical constituents(생존편향 보정). 구독=[[apis/eodhd/pricing_plan/PLANS|EOD Historical $19.99]](2026-06-18 결제·100k calls/day·30년+·**재무❌→EDGAR**)
  - **SEC EDGAR**(ticker→cik 식별·재무) [[apis/sec-edgar/_index|sec-edgar]] — `company_tickers.json`(현재 ticker→cik 10자리) + `companyfacts.json`(XBRL 재무 — `facts.{taxonomy}.{Concept}.units.{unit}[].{end,val,filed,fy,fp,form}`·PIT=filed·ROE/P/B concept). 키 없음·`User-Agent`(EDGAR_IDENTITY) 필수·~10req/s

## 🔬 리서치 (research/)

- [[research/2026-06-23-관측성-스택-버전|2026-06-23 관측성 스택 버전]] — prom v3.12.0(⚠️latest=2.x)·grafana 13.0.2·pushgateway·instrumentator 8.x(starlette1.3.1)·memray. 배치=Pushgateway·peak=tracemalloc+RSS·Local Snapshot·레이어 대시보드(tbbe-hub)
- [[research/2026-06-17-webapp-stack-버전|2026-06-17 webapp 스택 버전]] — Vite8/React19/TS6/router7/react-markdown10 + FastAPI0.137, API 표면 함정(urlTransform·runtimeCaching·CORS/Vite proxy·Starlette1.0 핀)
- [[research/2026-06-16-미국주식-데이터소스|2026-06-16 미국주식 데이터소스]] — **리서치 기준선**(가격 본격 소스는 [[decisions/ADR-003-M2-가격소스-EODHD|ADR-003]]에서 Sharadar SEP→**EODHD**로 개정) 가격 Tiingo→Sharadar SEP / 재무 EDGAR(filed=PIT) / SimFin·Polygon 비교, 미장 전환 시점 비교 노트
- [[research/2026-06-16-한국주식-데이터소스|2026-06-16 한국주식 데이터소스]] — 보류(미장 전환) 벌크=FDR+pykrx / 일일=KRX OpenAPI, 나중 한국장 추가 시 재사용
- ~~[[research/2026-06-12-스택-버전-리서치]]~~ — (구) Boot 4.1/Next 16, 도메인 전환으로 폐기

## 🛠️ 구현 히스토리 (work-history/)

> 모든 구현의 의도·계획(플랜 백업)·전후 비교. 인덱스: [[work-history/INDEX]]
> 템플릿: [[templates/work-history-template]] — src 변경 커밋에 엔트리 동반 (drift 강제)

## 📓 개발 일지 (dev-log/)

> 템플릿: [[templates/devlog-template]] — 막힌 것·결정·다음 할 일 기록

- [[dev-log/2026-06-12|2026-06-12]] — 프로젝트 세팅 (하네스·스캐폴딩·깃·검증·기획 v2)
- [[dev-log/2026-06-16|2026-06-16]] — M0 도메인·스택 전환(MCP→stockpick 한국주식, Java/Next→Python/PWA)·데이터소스 리서치·stock-1st_plan 확정

## 📚 투자 학습 노트 (learning/)

> ⚠️ 교육용 휴리스틱 — 검증된 알파 소스 아님(금융 BLOCKING). 매크로·연준·SEC 공시·재무제표 독해 기초.

- [[learning/README|학습 노트 인덱스]] — 추천 학습 순서·셀프체크
- [[learning/00.caveats|00 주의사항]] — 학습 자료를 알파로 오인하지 않기
- [[learning/01.macro-business-cycle/README|01 매크로 경기순환]] — 금리 사이클·섹터 로테이션
- [[learning/02.fed-and-treasury/README|02 연준·국채]] — 수익률 곡선(10y-2y) 스프레드
- [[learning/03.sec-filing-framework/README|03 SEC 공시 프레임워크]] — 공시 유형·항목
- [[learning/04.financial-statements/README|04 재무제표 읽는 법]] — 재무상태표·손익·현금흐름·연차보고서

## 템플릿

- [[templates/adr-template]] — 아키텍처 결정 기록
- [[templates/devlog-template]] — 개발 일지
- [[templates/research-template]] — 리서치 노트

## 외부 참조

- 하네스 가이드: `/home/code/project/claude-setting/`
- 발전형 하네스 실전: `/home/code/project/tbbe-hub/.claude/`
- GitHub: https://github.com/LJY981008/AgentGrid
