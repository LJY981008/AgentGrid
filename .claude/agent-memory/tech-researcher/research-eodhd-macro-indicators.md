---
name: research-eodhd-macro-indicators
description: EODHD Macro Indicators API 실측 — /macro-indicator/{country}·연간 World Bank WDI·39지표·10콜/요청·All-In-One/Fundamentals
metadata:
  type: reference
---

EODHD Macroeconomics Data & Macro Indicators API (2026-06-16 실측, r.jina.ai + 원본 직접 fetch 2출처 일치).

- 엔드포인트: `GET https://eodhd.com/api/macro-indicator/{country}` (단일 엔드포인트)
- path: country = ISO 3166-1 alpha-3 (USA/FRA/KOR 등, 대소문자 무관) + World Bank 집계(WLD/EUU 등)
- query: api_token(필수), indicator(기본 gdp_current_usd, 39종), fmt(json 기본/csv — csv는 소수 절삭)
- 응답: 연간 관측치 JSON 배열(최신→과거), 필드 CountryCode/CountryName/Indicator/Date(항상 12-31)/Period(항상 "Annual")/Value
- 콜 소비: 요청당 10콜. 플랜: All-In-One + Fundamentals Data Feed
- 함정: **연간 빈도 only**(분기/월 없음), World Bank 갱신 지연(참조연도 후 수개월), 지표별 국가 커버리지 불균등, 미지의 국가코드는 404 아닌 빈 배열
- stockpick 관련성: 한국 거시(KOR GDP/인플레/금리) 정성 보정용으로만 — 종목 알파 소스 아님. 연간이라 백테스트 시점성 한계

[[research-eodhd]] [[research-data-source-api-surface]]
