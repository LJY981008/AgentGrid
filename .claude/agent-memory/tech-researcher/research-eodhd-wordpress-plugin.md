---
name: research-eodhd-wordpress-plugin
description: EODHD WordPress plugin 페이지는 REST 명세 아님(shortcode 위주 개요). stockpick(Python) 무관
metadata:
  type: reference
---

EODHD `/financial-apis/wordpress-financial-stocks-crypto-market-data-plugin` 페이지 실측 (2026-06-16, r.jina.ai 경유 2회 교차확인):

- REST API 명세가 **아니다**. WordPress 사이트 임베드용 플러그인 개요 페이지.
- HTTP REST 엔드포인트 URL(`https://eodhd.com/api/...`) 일절 없음.
- 노출 인터페이스는 **shortcode** 3종: `[eod_fundamental target= id= preset=]`, `[eod_financials target= id= preset= years=]`, `[eod_news target= offset= limit=]`. (추가로 `[eod_ticker]` 라이브 가격 언급)
- API 키 필요: 데모 6티커(AAPL.US/TSLA.US/VTI.US/AMZN.US/BTC-USD.CC/EURUSD.FOREX), Free=20콜/일·최근1년만, 유료 $19.99~.
- **stockpick(개인 투자용 한국주식, Python) 와 무관** — WordPress 장식/임베드용. EODHD 커버리지 완결 차원의 기록.

관련: [[research-eodhd]] (EODHD 가격 API 본체)
