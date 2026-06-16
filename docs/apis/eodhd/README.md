# EODHD API 명세 (M2 본격 가격 소스 — [ADR-003](../../decisions/ADR-003-M2-가격소스-EODHD.md))

> 환각 방지 권위 레퍼런스. 캡처 2026-06-16(워크플로우 `eodhd-spec-capture`: 카탈로그 discover→62페이지 병렬 capture, SPA는 r.jina.ai 프록시). 6개월 주기 재캡처.
> 인덱스: [`_index.json`](_index.json). **62섹션 / 189 엔드포인트** (ok 54 / partial 8 / failed 0).

- **base_url**: `https://eodhd.com/api`
- **인증**: `?api_token=<KEY>` **쿼리 파라미터**(⚠️ Tiingo 의 `Authorization: Token` 헤더와 다름). 키=`.env` 의 `EODHD_API_KEY`. 데모 키 `api_token=demo` 는 한정 티커(AAPL.US 등)만.
- **심볼**: `{TICKER}.{EXCHANGE}` 형식(예 `AAPL.US`).
- ⚠️ 라이선스(개인·비배포)·해지 후 삭제 조항 — ADR-003 분석(재현성과 무관).

## stockpick 핵심 (relevant=true, 16섹션)

| 섹션 | 용도 | 핵심 |
|---|---|---|
| [end-of-day-historical-data](end-of-day-historical-data.json) | **M2 가격 주력** | `GET /api/eod/{SYMBOL}` — raw OHLC + `adjusted_close`(split+배당) + volume. `from`/`to`/`period`/`fmt`. adj_factor = adjusted_close/close |
| [delisted-stock-companies-data](delisted-stock-companies-data.json) | **생존편향** | 폐지종목 가격 2000~(개요 페이지 — EOD 엔드포인트에 폐지티커로 접근). 2018후 폐지=펀더멘털+actions, 이전=EOD only |
| [corporate-actions-splits-dividends](corporate-actions-splits-dividends.json) | 분할·배당 | adj_factor 검증·통일 |
| [bulk-api-eod-splits-dividends](bulk-api-eod-splits-dividends.json) | 벌크 | 거래소 전체 1요청 (⚠️partial — 보강 여지) |
| [search-api-stocks-etfs-mutual-funds](search-api-stocks-etfs-mutual-funds.json) · [exchanges-api-list-of-tickers-and-trading-hours](exchanges-api-list-of-tickers-and-trading-hours.json) · [covered-tickers-list](covered-tickers-list.json) | 유니버스 | iter_universe·티커목록 |
| [sp-dow-jones-historical-constituents](sp-dow-jones-historical-constituents.json) | **생존편향 보정** | 과거 시점 지수 편입종목(point-in-time 유니버스) |
| [us-stock-symbol-rename-history](us-stock-symbol-rename-history.json) | 식별자 연속성 | ticker 변경 추적(ticker_history 보강) |
| [fundamental-data-stocks-etfs-funds-indices](fundamental-data-stocks-etfs-funds-indices.json) | 재무(참고) | 주력은 EDGAR. EODHD는 보조 |
| general: [quick-start-guide](quick-start-guide.json) · [user-api](user-api.json) · [api-limits](api-limits.json) | 인증·한도 | 위 auth·rate limit |

## 비핵심 (relevant=false — 참고만)

intraday/tick/live/websocket · options · esg · insider · crypto · forex · news/sentiment · macro(bonds/rates/treasury/commodities) · screener · technical · calendar · SDK/언어예제 · marketplace 등. `_index.json` 의 `relevant_to_stockpick=false`.

> 코드 작성 시 `endpoints[].{url_pattern, method, query_params, response_fields}` 가 진실원천. `fetch_status`·`caveats` 확인. EodhdSource 어댑터(TASK-D)는 이 명세 준거.
