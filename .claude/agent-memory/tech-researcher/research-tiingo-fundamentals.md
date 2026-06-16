---
name: research-tiingo-fundamentals
description: Tiingo Fundamentals API 표면 실측 — 공식 페이지 JS렌더(읽기 실패), 래퍼/CRAN 교차로 엔드포인트 4종·auth·tier 확인 (2026-06-16)
metadata:
  type: project
---

Tiingo Fundamentals API (https://www.tiingo.com/documentation/fundamentals) 실측 결과.

**Why:** 미국주식 무료/유료 데이터소스 후보 검토 흐름([[research-us-free-data-sources]] Tiingo 포함, [[research-us-data-sources]])에서 Tiingo 재무 API 표면을 코드 참조용으로 확정 요청.

**How to apply:** Tiingo 재무 코드 작성 시 아래 4 엔드포인트만 신뢰. 단 공식 페이지 직접 검증은 미완(아래 한계).

- 공식 doc 페이지 전부 **클라이언트 사이드 렌더링** → WebFetch 직접은 `<title>`만 회수. web.archive.org/timetravel **차단**. **해결: `https://r.jina.ai/<url>` 프록시로 본문 정상 추출** ([[research-tiingo-spa-fetch-limit]] 동일 우회). 모든 Tiingo doc 은 이 프록시 사용.
- 교차검증: hydrosquall/tiingo-python `api.py`(공식 docstring 인용), readthedocs, matteoantoci/mcp-tiingo, CRAN riingo, dltHub.
- base_url `https://api.tiingo.com`, auth = HTTP 헤더 `Authorization: Token <key>` (래퍼는 `?token=` 도 사용 — 둘 다 동작 추정).
- 엔드포인트(GET): `tiingo/fundamentals/definitions` · `tiingo/fundamentals/{ticker}/daily` · `tiingo/fundamentals/{ticker}/statements` · `tiingo/fundamentals/meta`.
  - statements 핵심 param: `startDate`,`endDate`,`asReported`(true=릴리스시점 그대로/false=정정반영),`fmt`,(mcp는 year/quarter도). PIT(룩어헤드) 관점: asReported=true 가 시점정합. **금융 BLOCKING 관련 — false 면 restatement 덮어써 룩어헤드 위험**.
  - daily: marketCap 등 일일 갱신 지표, `startDate`,`endDate`,`columns`,`fmt`.
- tier: **무료 플랜 재무 미포함**. Power user(유료) add-on. 과거 beta 시 DOW30 만 평가용. 가격·rate limit 수치는 출처별 상이(시점 민감) — 공식 pricing 페이지 재확인 필요.
- 응답 스키마(공식 확인): definitions=dataCode/name/description/statementType(4종)/units. statements=date(공개일)/quarter(0=연간)/year/statementData{balanceSheet,incomeStatement,cashFlow,overview}[dataCode,value]. daily=date/marketCap/enterpriseVal/peRatio/pbRatio/trailingPEG1Y. meta=permaTicker(PK)/ticker/name/isActive/isADR/sector/industry/sicCode/.../statementLastUpdated/dailyLastUpdated.
- 커버리지(공식): 5,500+ 종목, 20년+, SEC 공개 후 12-24h 갱신, 모든 값 USD 환산(time-appropriate FX). 폐지종목은 permaTicker 로 접근(생존편향 회피 가능). 무료=DOW30 3년만.
- JSON(기본)=nested, CSV=flat 2-D. 함정: 컬럼/필드 순서 의존 파싱 금지(지표 추가 진행중). asReported=false→prior period 는 최신보고서값(정정반영, 룩어헤드위험), true→as-reported(시점정합).
