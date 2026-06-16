---
name: research-tiingo-crypto
description: Tiingo Crypto API 표면 — /crypto(meta)·/crypto/prices(OHLCV)·/crypto/top(top-of-book DEPRECATED). 문서 SPA 부분렌더 한계 (2026-06-16)
metadata:
  type: reference
---

Tiingo Crypto API ([[research-tiingo-api]] 공통규약 상속). 대상: tiingo.com/documentation/crypto. 2026-06-16 실측.

**문서 추출 한계 (중요)**: 이 페이지는 SPA — r.jina.ai 프록시가 **상단 top-of-book 섹션만** 렌더해 반환하고 /prices·metadata·websocket 하단부는 못 얻음(여러 번 재시도/캐시우회 모두 동일). web.archive.org는 WebFetch가 차단됨. → fetch_status=partial. /prices·/crypto·/top URL/파라미터는 **공식 클라이언트 소스(hydrosquall/tiingo-python api.py, riingo)** 로 보강 = 대상 문서 직접 인용 아님.

엔드포인트 (base_url https://api.tiingo.com, 인증 ?token= 또는 Authorization: Token):
- `GET /tiingo/crypto` — 메타데이터. params: tickers, format
- `GET /tiingo/crypto/prices` — OHLCV(historical+intraday). params: tickers, baseCurrency, startDate, endDate, exchanges, consolidateBaseCurrency, includeRawExchangeData, resampleFreq, convertCurrency. resampleFreq 예: 5min/1Hour/1day. 응답: ticker, baseCurrency, quoteCurrency + priceData[]: date, open, high, low, close, volume, volumeNotional, tradesDone
- `GET /tiingo/crypto/top` — top-of-book/last price. **DEPRECATED** (crypto 거래소 피드 신뢰성 문제로 일관된 bid/ask 구성 불가 사유). params: tickers, exchanges, includeRawExchangeData, convertCurrency. 응답: ticker, baseCurrency, quoteCurrency, topOfBookData{bid/ask}, exchangeData(includeRawExchangeData=true시), quoteTimestamp, lastSaleTimestamp, lastPrice, lastSize, bidPrice/bidSize/bidExchange, askPrice/askSize/askExchange

stockpick 함의: 도메인이 한국주식 — crypto는 직접 무관. 우선순위 낮음.
