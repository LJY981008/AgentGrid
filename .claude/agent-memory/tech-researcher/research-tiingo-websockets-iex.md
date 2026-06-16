---
name: research-tiingo-websockets-iex
description: Tiingo IEX WebSocket API 실측 — 엔드포인트·thresholdLevel·data 배열 인덱스 순서·IEX 2025-02-01 협약·플랜
metadata:
  type: reference
---

대상: `https://www.tiingo.com/documentation/websockets/iex` (SPA → r.jina.ai 프록시로 본문 확보, 2026-06-16). 직접 WebFetch는 제목만 — [[research-tiingo-spa-fetch-limit]].

**엔드포인트**: `wss://api.tiingo.com/iex` (base `wss://api.tiingo.com`, 형제 `/fx` `/crypto`).

**구독 메시지 형식은 이 페이지엔 없음**(NOT ON PAGE) — WS overview/connecting 페이지에 있고, 공식 ref client(hydrosquall/tiingo-python wsclient.py)로 확인: `{"eventName":"subscribe","authorization":"<API_KEY>","eventData":{"thresholdLevel":5,"tickers":[...]}}`. authorization 헤더 아닌 메시지 body 필드.

**응답**: service="iex", messageType="A"(새 가격호가). 이 페이지엔 A 외 코드(H/I/E) 미기재.

**thresholdLevel** (이 페이지 기재):
- 0 = ALL Top-of-Book + Last Trade (FULL TOPS)
- 5 = All Last Trade + major Quote updates만
- 6 = Reference Price 변경 감지 시 (IEX 라이선스 불필요)

**Full TOPS data 배열 인덱스 순서**(미확인이던 것 — 확정):
0 updateType(T/Q/B) · 1 date(ISO) · 2 nanoseconds(int64) · 3 ticker · 4 bidSize · 5 bidPrice · 6 midPrice · 7 askPrice · 8 askSize · 9 lastPrice · 10 lastSize · 11 halted · 12 afterHours · 13 ISO · 14 oddlot · 15 NMS Rule 611.
**Reference Price data 배열**: 0 date · 1 ticker · 2 referencePrice(float).

⚠️ **caveat**: 2025-02-01 IEX 정책 변경 — FULL TOPS(level 0/5) 수신엔 IEX Exchange와 체결한 market data agreement 필요. level 6(reference price)은 협약 불필요. 플랜: Free/Power/Commercial/Redistribution 모두 firehose 접근 가능(단 IEX 협약 게이팅 별도). rate limit/동시연결 수는 이 페이지에 없음.
