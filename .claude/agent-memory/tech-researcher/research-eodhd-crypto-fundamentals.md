---
name: research-eodhd-crypto-fundamentals
description: EODHD 암호화폐 펀더멘털 API 표면 실측 (fundamentals/{SYMBOL}.CC) — stockpick 한국주식엔 무관하나 EODHD 시리즈 완결용
metadata:
  type: reference
---

EODHD 암호화폐 펀더멘털 API (https://eodhd.com/financial-apis/fundamental-data-for-cryptocurrencies, 실측 2026-06-16, r.jina.ai 프록시 경유 — SPA라 직접 WebFetch 빈 본문 위험).

- 엔드포인트: GET `https://eodhd.com/api/fundamentals/{SYMBOL}.CC` (예 BTC-USD.CC). 일반 fundamentals 경로 공유, `.CC` 서픽스로 암호화폐 식별
- 인증: `?api_token=<KEY>`. demo 토큰은 BTC·ETH만
- 콜 소비: **요청당 10 API calls** (EODHD historical-market-cap 과 동일 가중)
- 플랜: **All-In-One** + **Fundamentals Data Feed**
- 응답 섹션: General(Name/Type="Crypto"/Category coin|token/WebURL/Description) · Tech.Developers(이름-역할 문자열 배열) · Resources.Links(website/reddit/youtube/explorer/facebook/source_code) + Thumbnail(128x128, finage S3 호스팅) · Statistics(MarketCapitalization/Diluted, CirculatingSupply/Total/Max Supply, MarketCapDominance%, TechnicalDoc/Explorer/SourceCode/MessageBoard URL, LowAllTime/HighAllTime 가격)
- stockpick(한국 코스피/코스닥) 도메인엔 직접 무관 — EODHD API 표면 완결 기록용. [[research-eodhd]] [[research-eodhd-historical-marketcap]] 계열
