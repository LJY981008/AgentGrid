---
name: research-eodhd-historical-marketcap
description: EODHD Historical Market Cap API 실측 — /historical-market-cap/{TICKER}, 주간 period, 2020~, US만, 10콜/요청, All-In-One/Fundamentals 플랜
metadata:
  type: reference
---

EODHD Historical Market Capitalization API (2026-06-16 실측, r.jina.ai 프록시 경유 — 페이지는 SPA).

- 엔드포인트: GET `https://eodhd.com/api/historical-market-cap/{TICKER}` (base_url `https://eodhd.com/api/`)
- TICKER = `{SYMBOL}.{EXCHANGE}` (US는 .US 생략 가능)
- 쿼리: `api_token`(필수), `fmt`(예시 json), `from`/`to`(YYYY-MM-DD)
- 인증: `?api_token=<KEY>`, demo 키는 AAPL.US만
- **주간(weekly) period — daily 아님** (페이지 명시)
- 커버리지: NYSE/NASDAQ US 주식 **2020년부터** (크립토 예정). → 30년 백테스트엔 부적합(2020~)
- 소비: **요청당 10 API 콜**, 일일 10만 요청
- 플랜: All-In-One + Fundamentals Data Feed
- **caveat**: 응답 필드명(date/value 등)이 페이지에 텍스트로 안 적힘 — 이미지로만. 추측 금지.

관련: [[research-eodhd]] (EOD All World 가격 엔드포인트)
