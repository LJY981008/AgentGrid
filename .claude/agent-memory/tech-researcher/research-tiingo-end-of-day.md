---
name: research-tiingo-end-of-day
description: Tiingo End-of-Day(/tiingo/daily) API 표면 실측 — 엔드포인트3(meta/latest/historical)·OHLCV+조정컬럼·CRSP방식·resampleFreq (2026-06-16)
metadata:
  type: reference
---

Tiingo End-of-Day(EOD) 주가 API. 출처: tiingo.com/documentation/end-of-day (JS SPA — r.jina.ai 렌더 프록시 경유 확보, web.archive.org 는 WebFetch 차단됨). 2026-06-16 실측. 공통 규약은 [[research-tiingo-api]].

- base_url: `https://api.tiingo.com/tiingo/daily`
- 엔드포인트 3종 (모두 GET):
  1. Meta Data: `GET /tiingo/daily/{ticker}` → ticker,name,exchangeCode,description,startDate(최초 데이터일),endDate(최신 데이터일)
  2. Latest Price: `GET /tiingo/daily/{ticker}/prices` (파라미터 없으면 최신 1건)
  3. Historical: `GET /tiingo/daily/{ticker}/prices?startDate=&endDate=&format=&resampleFreq=`
- 가격 응답 필드(price 객체): date, open, high, low, close, volume, adjOpen, adjHigh, adjLow, adjClose, adjVolume, divCash, splitFactor
- 조정주가 방식: raw·adjusted 둘 다 제공, split/dividend 조정은 **CRSP 방법론** 따름 (문서 명시). → stockpick 수정주가 통일 시 adj* 사용, divCash/splitFactor 로 이벤트 추적 가능.
- format: json(기본, 메타 포함) | csv. resampleFreq: 페이지엔 monthly 예시만 명시(daily/weekly/annually 등은 페이지 미기재 — 추측 금지).
- 인증: **이 페이지 자체엔 미기재**. 공통 규약([[research-tiingo-api]])대로 ?token= 또는 Authorization: Token 헤더.
- caveats: columns/sort 파라미터 페이지 미기재. resampleFreq 전체 허용값 페이지 미캡처. EOD 무료/유료 한도(Power add-on 등)는 이 페이지 미기재 — pricing/[[research-tiingo-fundamentals]] 참조. 날짜 예시 형식 YYYY-M-D(zero-pad 불요로 보이나 명시 없음).
