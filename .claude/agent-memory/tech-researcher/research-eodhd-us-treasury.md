---
name: research-eodhd-us-treasury
description: EODHD US Treasury (UST) Interest Rates API(beta) 표면 실측 — 4엔드포인트·filter[year]·1콜/요청·Free플랜포함·한국주식무관
metadata:
  type: reference
---

EODHD US Treasury (UST) Interest Rates API (beta) — 2026-06-16 실측 (r.jina.ai 프록시, 본문/코드블록/JSON 예시 텍스트 완전 렌더 확인).
출처: https://eodhd.com/financial-apis/us-treasury-ust-interest-rates-api-beta

- base_url: `https://eodhd.com/api/ust/`
- 엔드포인트 4종(모두 GET):
  - `/ust/bill-rates` — T-Bill discount/coupon/avg_*/maturity_date/cusip/tenor. 유일하게 page[limit]·page[offset] 페이지네이션 예시 있음
  - `/ust/long-term-rates` — Daily Treasury Real Long-Term Rate Averages + Long-Term Rates 결합. 필드 date/rate_type(BC_20year,Over_10_Years,Real_Rate)/rate/extrapolation_factor(null 가능)
  - `/ust/yield-rates` — Par Yield Curve (nominal). date/tenor(1M..10Y)/rate
  - `/ust/real-yield-rates` — Par Real Yield Curve. date/tenor(5Y/10Y/20Y/30Y)/rate
- 인증: `?api_token=YOUR_TOKEN` 쿼리(필수)
- 공통 파라미터: `filter[year]`(int, 1900~현재+1, 미지정시 현재연도), `fmt=json`(예시에 등장)
- 응답: `{ "meta": {"total": N}, "data": [...] }` JSON. ⭐예시 JSON·필드표가 이미지 아닌 텍스트로 실재(이전 EODHD 페이지들과 달리 환각아님 확인됨)
- API콜: 1콜/요청
- 플랜: All-In-One, EOD All World, EOD+Intraday All World Extended, **Free 플랜 포함**
- ⚠️ beta. 미국 국채 데이터 → stockpick(한국주식)엔 무위험금리 베이스라인 정도 외 직접무관. 완결성용 기록
