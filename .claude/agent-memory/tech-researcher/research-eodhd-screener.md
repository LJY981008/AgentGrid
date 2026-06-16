---
name: research-eodhd-screener
description: EODHD Stock Market Screener API 표면 — filters/signals/sort 파라미터·콜소비·플랜·응답JSON 이미지only 한계
metadata:
  type: reference
---

EODHD Stock Market Screener API (https://eodhd.com/financial-apis/stock-market-screener-api, 2026-06-16 실측, r.jina.ai 프록시 경유 — eodhd.com SPA).

- 엔드포인트: `GET https://eodhd.com/api/screener` (단일). base_url = https://eodhd.com/api
- 인증: `?api_token=<KEY>` 쿼리 ([[research-eodhd]] 공통)
- 핵심 파라미터:
  - `filters` = `[["field","operation",value],...]` JSON 배열 문자열
  - `signals` = 콤마구분 시그널 (200d_new_lo/hi, bookvalue_neg/pos, wallstreet_lo/hi)
  - `sort` = `field.asc|desc`
  - `limit` 1~100 (기본 50), `offset` 0~999 (기본 0)
- String 필드(code,name,exchange,sector,industry) 연산: `=`, `match`
- Numeric 필드(market_capitalization,earnings_share,dividend_yield,refund_1d_p,refund_5d_p,avgvol_1d,avgvol_200d,adjusted_close) 연산: `=`,`>`,`<`,`>=`,`<=`
- 콜 소비: **요청당 5콜**. 플랜: All-In-One / EOD+Intraday / All World Extended
- ⚠️ 함정: 응답 JSON 필드 스키마가 페이지에 텍스트로 없음(이미지 "Image 18" only) → 필드명 미확정. fetch_status=partial
- stockpick 관련성: 미국 등 글로벌 스크리닝용. KRX(한국) 커버리지는 별도 확인 필요 — screener의 exchange 필터에 KRX 포함 여부 페이지 미기재
