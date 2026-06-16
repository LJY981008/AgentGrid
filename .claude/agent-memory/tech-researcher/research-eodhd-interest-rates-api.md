---
name: research-eodhd-interest-rates-api
description: EODHD Interest Rates API (정책금리/무위험금리) REST 명세 — reference-rates/policy-rates 2엔드, filter[]/page[] 파라미터, T+1, KRX 무관
metadata:
  type: reference
---

EODHD Interest Rates API 실측 (2026-06-16, r.jina.ai 프록시 2회 교차검증, eodhd.com SPA 직접 fetch는 빈본문 우려).

source: https://eodhd.com/financial-apis/interest-rates-api-sofr-fed-funds-ecb-boe-policy-rates

- base_url: `https://eodhd.com/api/rates/` (다른 EODHD 엔드와 달리 /api/rates/ 하위)
- auth: `?api_token=YOUR_TOKEN` 쿼리
- **JSON:API 스타일 파라미터** — 다른 EODHD 엔드(`?filter=`, `?from=`)와 다르게 `filter[code]`, `filter[currency]`, `filter[from]`, `filter[to]`, `page[limit]`(기본20,최대100), `page[offset]`(기본0). 대괄호 표기 함정 주의.
- 엔드 2개:
  1. `/reference-rates` — 무위험 기준금리 (SOFR/EFFR/OBFR/TGCR/BGCR/SOFR30D/90D/180D/INDEX/SONIA/ESTR). USD/GBP/EUR. NY Fed 행만 percentiles{p1,p25,p75,p99}+volume_billion_usd.
  2. `/policy-rates` — 중앙은행 정책금리 (FED_TARGET_LOWER/UPPER, ECB_DFR/MRO/MLF, BOE_BANK_RATE). filter[country]=US/EU/GB, filter[central_bank]=FED/ECB/BOE.
- 콜소비: 둘 다 "1 API call per request"
- 갱신: **Daily, T+1** (소스 발표 1영업일 뒤)
- 상태코드: 200 / 401(토큰무효) / 403(플랜에 rates 미포함) / 422(파라미터 오류)
- pricing: 페이지에 **플랜 포함 여부 미명시**. 403 설명으로 별도 rates 접근권 존재만 암시.
- ⚠️ stockpick(KRX) 무관 — 미/영/유로 금리만. 매크로 보조지표로도 한국 통화정책(BOK) 미포함이라 직접 효용 낮음. EODHD 명세 완결성 목적 기록.
