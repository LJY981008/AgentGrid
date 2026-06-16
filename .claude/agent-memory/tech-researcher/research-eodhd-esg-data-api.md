---
name: research-eodhd-esg-data-api
description: EODHD ESG Data API (InvestVerte 마켓플레이스) 엔드포인트·콜소비·플랜 실측 (2026-06-16)
metadata:
  type: reference
---

EODHD ESG Data API = InvestVerte 마켓플레이스 제품. 메인 EODHD API 와 별개 마켓플레이스 구독.

- base_url: `https://eodhd.com/api/mp/investverte/` (메인 `/api` 가 아닌 `/api/mp/{vendor}/` 경로 — 마켓플레이스 공통)
- 엔드포인트 6종: companies, countries, country/{symbol}, esg/{symbol}, sectors, sector/{symbol}
- 응답: 회사 ESG = e/s/g/esg(점수) + year + frequency. 국가 = symbol/name/mean/median + year/frequency
- 쿼리: year, frequency(FY/Q1~Q4), model(ai 기본/legacy). 인증 api_token, 스킴명 "EODToken"
- ⚠️ 콜 소비: 1 request = 10 API calls (마켓플레이스 기준 24h 카운트가 메인 플랜과 다름). 100k calls/24h, 1000 req/min
- 가격: $29.99/mo ($50 first 3mo). 별도 마켓플레이스 구독 — All-In-One 포함 여부 문서 미기재
- ⚠️ 함정: stockpick 은 한국주식(KRX) 도메인. ESG 커버리지(국가/회사 범위) 문서 미명시 — KRX 종목 지원 불확실. 직접 활용 전 검증 필요
- 문서 SPA → r.jina.ai 프록시 경유로 본문 확보. 랜딩(/financial-apis/esg-data-api)은 마케팅, 실docs는 /marketplace/investverte/esg_data/docs
