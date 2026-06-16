---
name: research-tiingo-iex
description: Tiingo IEX API 표면 실측 — 실시간 호가/체결·과거 인트라데이 가격 엔드포인트·필드·2025 IEX 정책변경(TOPS 게이팅) (2026-06-16)
metadata:
  type: reference
---

Tiingo IEX 엔드포인트 ([[research-tiingo-api]] 공통규약 상속). 출처: tiingo.com/documentation/iex (JS SPA — r.jina.ai 렌더 프록시 경유 verbatim, 2회 일관). web.archive.org는 차단됨. 2026-06-16 실측.

- base_url `https://api.tiingo.com` (공통). 인증: `?token=` 또는 `Authorization: Token X` (공통규약, IEX 페이지엔 미기재).
- 엔드포인트 3종:
  - `GET /iex` — 전 티커 top-of-book/last
  - `GET /iex/<ticker>` — 특정 티커 top-of-book/last
  - `GET /iex/<ticker>/prices?startDate=2019-01-02&resampleFreq=5min` — 과거 인트라데이 OHLCV
- 실시간 응답 필드: ticker, timestamp, quoteTimestamp, lastSaleTimestamp, last, lastSize, tngoLast(last 또는 mid), prevClose, open, high, low, mid((bid+ask)/2), volume, bidSize, bidPrice, askSize, askPrice. → quote/last/bid/ask 필드는 **IEX entitlement 필요**, tngoLast/open/high/low/mid는 Tiingo 계산값(비등록자도 가능).
- 인트라데이 prices 필드: date, open, high, low, close, volume. **volume은 columns 파라미터로 명시 요청해야만 노출**.
- 쿼리 파라미터: IEX 페이지에 명시된 것 = `resampleFreq`(예시 5min, 허용값 열거 안 됨), `startDate`(예시 2019-01-02), `columns`(예: open,high,low,close,volume). endDate/format/afterHours/forceFill 등은 IEX 페이지에 **미기재**(daily 페이지엔 있으나 IEX엔 없음 — 지어내지 말 것).
- ⚠️ 2025-02-01 IEX 정책변경: FULL TOPS 피드 받으려면 IEX Exchange와 market data agreement 서명 필수. 비등록 고객은 derived reference price feed(tngoLast 등 Tiingo 계산값)만.
- 함정: SPA라 WebFetch 직접 호출 시 <title>만. resampleFreq 분/시간 단위 허용값은 페이지에 없어 코드에서 추측 금지 — 필요시 daily 페이지/실호출 검증.
