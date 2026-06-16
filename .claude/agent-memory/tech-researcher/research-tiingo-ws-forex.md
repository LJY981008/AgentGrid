---
name: research-tiingo-ws-forex
description: Tiingo Forex Websocket API 실측 — wss://api.tiingo.com/fx, subscribe JSON, FX data 배열 필드 순서 (2026-06-16)
metadata:
  type: reference
---

Tiingo Forex WS API. 대상 페이지 tiingo.com/documentation/websockets/forex (JS SPA — [[research-tiingo-spa-fetch-limit]]). r.jina.ai 프록시로 메시지구조/필드표 verbatim 확보, 연결/subscribe는 공식 페이지 WebSearch 인용 + reference client wsclient.py 교차검증. 2026-06-16.

- 엔드포인트: `wss://api.tiingo.com/fx` (base `wss://api.tiingo.com`, path 검증값 iex/fx/crypto). top-of-book + last trade.
- subscribe: `{"eventName":"subscribe","authorization":"<API_KEY>","eventData":{"thresholdLevel":5}}`. **인증은 authorization 키(eventData 아닌 최상위)에 API 키 직접**. thresholdLevel=5 → 모든 Top-of-Book 업데이트.
- 응답: `{"service":"fx","messageType":"A","data":[...]}`. service=항상 "fx". messageType="A"=새 가격 quote, "H"=heartbeat.
- **FX data 배열 인덱스 순서(verbatim, 공식 페이지)**: [0] updateType="Q"(quote) / [1] ticker / [2] datetime ISO / [3] bidSize / [4] bidPrice / [5] midPrice=(bidPrice+askPrice)/2.0 / [6] askPrice / [7] askSize.
  - ⚠️ 이전 메모리(spec-tiingo-spa)의 순서(midPrice 앞쪽, bidSize/bidPrice/askSize/askPrice 별도순)는 **오류 — 이 표가 실측 정답**.
- 미확인(대상 페이지서 미확보): thresholdLevel 전체 허용값 범위·기본값, tickers 파라미터 지원여부(client 예시엔 thresholdLevel만), heartbeat 주기 수치, unsubscribe 포맷, U/D/I/E 메시지타입, rate limit·무료/유료 차이. reference client는 파싱을 콜백에 위임해 추가정보 없음.
