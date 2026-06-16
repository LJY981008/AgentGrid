---
name: research-tiingo-spa-fetch-limit
description: Tiingo 공식 문서(www.tiingo.com/documentation/*)는 SPA라 WebFetch가 제목만 반환 — 우회법
metadata:
  type: reference
---

Tiingo 공식 API 문서 페이지(`https://www.tiingo.com/documentation/...`)는 JavaScript 렌더링 SPA여서 WebFetch로는 본문이 안 잡히고 페이지 제목("Stock Market Tools | Tiingo")만 반환된다. `api.tiingo.com/documentation/...`는 301로 www로 리다이렉트.

**우회법(권위 순)**:
1. 공식 reference client 소스 = 가장 정확한 와이어 프로토콜: `raw.githubusercontent.com/hydrosquall/tiingo-python/master/tiingo/wsclient.py` (Python), `victor-david/restless-tiingo` (.NET)
2. readthedocs `tiingo-python.readthedocs.io/en/latest/usage.html` (일부만, "Under Construction")
3. WebSearch 스니펫이 공식 페이지 문장을 직접 인용해줄 때가 있음

**실측 확인된 WS 프로토콜(2026-06-16)**: base `wss://api.tiingo.com`, 엔드포인트 `/fx` `/iex` `/crypto`. subscribe = `{"eventName":"subscribe","authorization":"<API_KEY>","eventData":{"thresholdLevel":5}}`. thresholdLevel 높을수록 업데이트 적음, 5=모든 Top-of-Book. 응답 = service/messageType(A=quote, H=heartbeat)/data 배열. FX 필드: ticker, timestamp, midPrice, bidSize, bidPrice, askSize, askPrice.

⚠️ WS data 배열의 정확한 인덱스 순서는 공식 페이지를 못 읽어 미확인 — 코드 참조 전 재확인 필요. 관련 [[research-us-free-data-sources]] (Tiingo 무료한도).
