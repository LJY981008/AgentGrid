---
name: research-eodhd-exchanges-trading-hours
description: EODHD Exchanges API 거래시간·휴장일 — v2/v1 exchange-details 엔드포인트, 콜소비, 플랜, KRX 적용 가능성
metadata:
  type: reference
---

EODHD "Exchanges API: Trading Hours and Stock Market Holidays" 실측 (2026-06-16, r.jina.ai 경유).
source: https://eodhd.com/financial-apis/exchanges-api-trading-hours-and-stock-market-holidays

- base_url: https://eodhd.com/api/, 인증 ?api_token=<KEY>
- 콜 소비: "Each request consumes 5 API calls per ticker"
- 플랜: All-In-One, EOD+Intraday — All World Extended
- 엔드포인트 3종:
  - v2 list: /api/v2/exchange-details (지원 거래소 코드 배열)
  - v2 detail: /api/v2/exchange-details/{CODE} — pre/after-hours, lunch break, early close, IANA tz, 검증된 휴장일(73개 거래소). 휴장일은 날짜 key 객체
  - v1 legacy: /api/exchange-details/{CODE} — from/to(기본 ±6개월), isOpen 실시간 상태, OperatingMIC, ActiveTickers. 휴장일은 Date 필드 인덱스 배열
- stockpick 적용: 한국 거래소 코드 KO(코스피)/KQ(코스닥) 커버리지는 이 페이지에 명시 안 됨 — 휴장일 캘린더(임시공휴일·대체휴일) KRX 적용 가능 여부는 별도 실측 필요. 룩어헤드 무관(정적 캘린더)이나 과거 임시휴장 정확도 미검증
- caveat: r.jina.ai 가 응답 표를 재구성 — 응답 필드명/타입 일부는 프록시 정규화 가능성. archive.org 교차검증은 451 차단으로 실패
