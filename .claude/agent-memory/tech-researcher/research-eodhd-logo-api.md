---
name: research-eodhd-logo-api
description: EODHD Stock Market Logos API 실측 — /api/logo/{symbol} PNG 200x200, 1req=10calls, $299/yr 별도, KQ/KO 한국포함이나 stockpick엔 장식용
metadata:
  type: reference
---

EODHD Stock Market Logos API (Unicornbay marketplace) — 2026-06-16 실측.

- 엔드포인트 1개: `GET https://eodhd.com/api/logo/{symbol}?api_token=<KEY>`
- symbol = `{ticker}.{exchange}` (예 AAPL.US)
- 응답: image/png 바이너리, 200x200px 투명배경. JSON 응답필드 없음. SVG 는 별도 product (SVG extension)
- 콜 소비: **1 API request = 10 API calls** (rate: 100,000 calls/24h, 1,000 req/min)
- 가격: $299/year 별도 마켓플레이스 구독 (메인 플랜 미포함, 별도)
- 커버리지: 40,000 로고, 60+ 거래소. 지원 거래소에 **KQ(코스닥), KO(코스피)** 포함 → 한국주식 로고 가능
- 문서: https://eodhd.com/marketplace/unicornbay/logo/docs (마케팅 페이지 https://eodhd.com/financial-apis/40-000-stock-market-logos-api 는 본문 빈약, docs 링크로 이동)

**stockpick 관련성**: 시장 데이터 아님 — 회사 로고 이미지뿐. 백테스트/룰/수집과 무관, 웹앱(M4) UI 장식용으로만 의미. 별도 유료라 채택 권고 안 함.
