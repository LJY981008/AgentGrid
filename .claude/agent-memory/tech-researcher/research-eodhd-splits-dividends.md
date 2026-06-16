---
name: research-eodhd-splits-dividends
description: EODHD splits/dividends API 표면 — /div/와 /splits/ 엔드포인트, JSON 키 실측, value(수정)/unadjustedValue 분리, 폐지종목·30년·콜소비량 미명시
metadata:
  type: reference
---

EODHD Corporate Actions (Splits & Dividends) API — https://eodhd.com/financial-apis/api-splits-dividends (2026-06-16 실측, Jina 프록시 + demo 엔드포인트 직접 호출).

base_url: https://eodhd.com/api/ · auth: ?api_token=<KEY> (demo는 AAPL.US만)

**2 엔드포인트** (둘 다 GET, query: from/to(Y-m-d), api_token, fmt=json|csv 기본 csv):
- `/div/{SYMBOL}.{EXCHANGE}` — 배당. JSON 키 실측: date, declarationDate, recordDate, paymentDate, period(예 "Quarterly"), value(수정후), unadjustedValue(수정전), currency. CSV는 Date,Dividends만(기본 필드).
  - ⚠️ value = 수정값, unadjustedValue = 당시 실제 지급액. 룩어헤드/수정 통일 시 구분 필수.
- `/splits/{SYMBOL}.{EXCHANGE}` — 분할. JSON 키 실측: date, split(문자열 "2.000000/1.000000" 형식 — 분수). 파싱 필요.

**플랜**: 무료는 support 문의로 1년치만 활성화. 유료는 30년+. 별도 bulk(다종목) 엔드포인트 언급(이 페이지엔 미상세).
caveats: 콜 소비량/일일한도 이 페이지에 미명시(EODHD 공통 규약은 [[research-eodhd]] 참조 — EOD가격은 호출당 1콜). split 비율이 raw 문자열이라 직접 분해. extended 배당필드(declaration/record/payment/unadjusted)는 주요 美/유럽 티커 + JSON 한정.

가격 데이터 본체는 [[research-eodhd]] (EOD All World, 폐지종목 2000~, 해지후 1개월 삭제의무 재현성 함정).
