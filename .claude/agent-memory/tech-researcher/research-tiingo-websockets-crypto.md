---
name: research-tiingo-websockets-crypto
description: Tiingo WebSocket crypto 엔드포인트 — wss URL·subscribe 구조·data 배열 필드(T/Q) 실측
metadata:
  type: reference
---

Tiingo WebSocket crypto 문서(`www.tiingo.com/documentation/websockets/crypto`) 실측 (2026-06-16).

**프록시 한계**: jina 프록시(`r.jina.ai`)는 이 SPA 페이지의 **하단 data 필드 표만** 일관되게 렌더링하고, 상단 연결/wss URL/subscribe/thresholdLevel 섹션은 누락시킨다. web.archive.org는 WebFetch 차단됨. 따라서 연결·인증부는 공식 reference client(`hydrosquall/tiingo-python/tiingo/wsclient.py`)로 보강 — 대상 페이지 직접 인용 아님.

**확보(공식 페이지 본문)**: service="crypto_data", messageType(항상 "A"=새 호가, "H"=heartbeat). Trade(T) 배열: [0]type "T" [1]ticker [2]date [3]exchange [4]lastSize(base currency) [5]lastPrice. Top-of-Book(Q) 배열: [0]type [1]ticker [2]date [3]exchange [4]bidSize [5]bidPrice [6]midPrice=(bid+ask)/2 [7]askSize [8]askPrice.

**보강(wsclient.py)**: base `wss://api.tiingo.com`, endpoint 경로 = `/crypto` (iex/fx/crypto 중). subscribe on_open 시 전송: `{"eventName":"subscribe","authorization":"<API_KEY>","eventData":{"thresholdLevel":5}}`. 인증은 authorization 필드(=API 키)를 구독 메시지 본문에 실음(헤더 아님). 관련 [[research-tiingo-spa-fetch-limit]] [[research-tiingo-api]].
