---
name: research-sec-edgar-free-financials
description: SEC EDGAR data.sec.gov XBRL API(companyfacts/concept/frames/submissions) 무료 재무층 실측 — filed=PIT가능, frames PIT함정, company_tickers는 현재활성만(폐지종목 매핑X), 정규화공수, edgartools 5.36(2026-06) (2026-06-16).
metadata:
  type: reference
---

2026-06-16 실측. SimFin 폴백용 무료 재무층 타당성. SEC 메인(sec.gov)은 WebFetch 403 — data.sec.gov API는 정상, 서드파티 2+출처 교차검증.

**API 표면** (전부 무료·API키 불필요, JSON):
- companyfacts: `data.sec.gov/api/xbrl/companyfacts/CIK{10자리}.json` — 한 회사의 모든 us-gaap concept 전체 기간. facts→taxonomy(us-gaap/dei)→concept→units(USD 등)→배열[{end,val,accn,fy,fp,form,filed,frame,(start)}]
- companyconcept: `.../companyconcept/CIK{cik}/{taxonomy}/{concept}.json` — 한 회사·한 concept 전 기간
- frames: `.../xbrl/frames/us-gaap/{concept}/{unit}/CY{YYYY}Q{Q}I.json` — **한 concept을 한 기간 전 종목 횡단**. I=instant(잔액), 미접미=duration(플로우)
- submissions: `data.sec.gov/submissions/CIK{cik}.json` — filing 이력+메타(tickers, former names, SIC). 폐지/미신고 entity도 포함

**PIT (disclosed_at)**:
- ✅ companyfacts/concept의 모든 fact에 `filed`(공시일) 있음 → financial.disclosed_at=filed, disclosed_at<=t 룩어헤드 회피 가능. accn(접근번호)·fy·fp·form(10-K/10-Q)도 동반
- ⚠️ **frames API는 PIT 깨질 위험**: 정의가 "각 entity가 해당 기간에 *last filed* most closely fits" — restatement 후 최신값을 줄 수 있음(as-reported 보장X). PIT 백테스트엔 companyfacts/concept(filed별 원본)을 쓰고 frames는 횡단 탐색용으로만. 같은 period에 amended 값 섞임 주의

**생존편향(우수)**:
- ✅ EDGAR 폐지/파산사 filing **영구보존**(1994~현재), CIK **재사용 안 함** → 폐지종목 재무 접근 가능(BLOCKING 충족)
- ⚠️ 단, **XBRL 구조화 재무는 2009~만**(그 전은 텍스트). 2009 이전 폐지사는 구조화 재무 없음
- ⚠️ **company_tickers.json은 현재 활성 ticker만** → 폐지종목 ticker→CIK 매핑 불가. ticker는 재사용됨(폐지 후 타사가 재취득). 폐지종목은 CIK 직접 보유 필요 → 별도 ticker-CIK 히스토리 매핑 인프라 자체구축 부담. (Sharadar는 이걸 풀어줌 — 대비 우위 사라짐)

**커버리지 단계적**: XBRL 의무화 시총별 3단계 — 2009 대형가속(public float>$700M) / 2010 가속 / 2011 소형보고사(float<$75M, 2011-06-15 이후 종료기간) / 2012 전체. **소형주는 2011~** 포함. 그 전 소형주 데이터 공백 = 잠재 생존편향 잔존

**정규화 공수(핵심)**:
- 태그 다양성 실재: 같은 매출도 RevenueFromContractWithCustomerExcludingAssessedTax / Revenues / SalesRevenueNet 등 회사·연도별 상이. raw companyfacts 직접은 Fallback Dictionary(타겟 ~15필드, 각 필드당 후보 태그 우선순위 리스트) 자체 구축 필요 — 중간 공수
- frames API는 *한 concept* 횡단만 풀어줌. 회사가 그 concept을 안 쓰면(다른 태그) 누락 → frames 단독으로 정규화 미해결
- **edgartools(라이브러리)가 standardize 제공**: `standard_concept` 컬럼이 line item을 표준 카테고리(Revenue/CommonEquity 등) 매핑, 계산 weight 정규화(R&D 부호 통일). 횡단 비교용 statement stitching. → 자체 Fallback Dictionary 부담 상당 경감

**rate/벌크/User-Agent**:
- fair access **10 req/s**(전 EDGAR 도메인 합산). 초과 시 차단
- **User-Agent 필수**: `회사명 이메일` 형식. 없으면 거부
- **벌크 = Financial Statement Data Sets**(분기/2024-03~월간) 2009q1~ zip. 면(face) 수치 / Notes 데이터셋은 텍스트+상세. API 안 긁고 일괄 적재 가능 → 30년(실제 2009~, 17년) 벌크 적합

**라이브러리 성숙도**:
- **edgartools 5.36.0(2026-06-09 릴리스, Py3.10~3.14, MIT, 매우 활발)** — rate-limit aware+캐싱+이메일 식별 자동, standardize 재무. 1순위 권장
- sec-edgar-api 1.1.0 — 얇은 래퍼(get_company_facts/concept/frames/submissions), 10 req/s 자동, User-Agent 강제. 정규화는 안 해줌
- license: 미 정부 퍼블릭 도메인 — 재배포·상업 제약 없음(EDGAR 데이터 자체). 단 fair-access 한도 준수 조건

**미확인/재검증**: frames의 amended 혼입 실제 빈도, edgartools standardize의 ~15타겟 필드 커버 정확도(자체 매핑 vs 비교 검증 필요), 2009~2011 소형주 공백이 실제 백테스트 모집단에 주는 영향. 6개월 주기.

**SimFin 대비 위치**: 무료·폐지종목·filed PIT는 충족하나 (1)2009~만(SimFin도 유사) (2)ticker-CIK 히스토리·정규화 자체부담 → edgartools로 완화. 폴백으로 타당하나 정규화/매핑 공수가 SimFin보다 큼.
