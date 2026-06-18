# EODHD 플랜별 허용 기능

> 출처 (EODHD Pricing plans 페이지 캡처, Monthly 기준). 진실원천 = 캡처 이미지. 정리: 2026-06-18.
> - `01-prices-limits.png` — 5개 플랜 가격 · API 한도 · 데이터 범위
> - `02-stocks-etf-funds.png` — AI&Dev Tools · Stocks/ETF/Funds · Forex/Crypto
> - `03-realtime-extended-exchanges.png` — Real-Time Websockets · Extended Data · Exchanges
> - `04-fundamentals-packages-support.png` — Fundamental Data · Additional Packages · Support

## 우리 플랜 = **EOD Historical Data — All World ($19.99/mo)**

근거: 캡처에서 이 플랜만 버튼이 **Unsubscribe**(나머지는 Upgrade / Pay with VISA) → 현재 구독 중.

**한 줄 요약 — 우리가 쓸 수 있는 것:**
- ✅ 미국+전세계 거래소 **일봉(EOD)** · 수정주가(Adjusted) · 분할/배당 · **폐지종목(Delisted)** 데이터
- ✅ 15분 지연 라이브 · US Extended 라이브 · Forex/Crypto EOD+1분지연
- ✅ Search API · 거래소/티커 목록 · ChatGPT Assistant · MCP Server · Financial News Feed
- ✅ 100,000 calls/day · 1,000 req/min · 데이터 범위 30년+
- ❌ **Fundamental Data(재무) 없음** · Intraday API 없음 · Technical/Screener API 없음 · Websocket 실시간 없음 · Real-time API 없음

> ⚠️ 금융 BLOCKING 연관: 우리 플랜은 **Delisted Data ✓**(생존편향 회피 가능) + **Adjusted ✓**(수정주가 통일) 충족.
> 단 **재무(Fundamentals)는 EODHD에 없음** → 재무는 SEC EDGAR(filed=PIT)에서 직접 파싱([ADR-005], [ADR-002]). EODHD는 가격 전용.

---

## 5개 플랜 가격

| 플랜 | 가격/월 | 버튼 | 비고 |
|---|---|---|---|
| Free Package | $0 | Upgrade | 20 calls/day, 과거 1년치만 |
| **EOD Historical Data — All World** | **$19.99** | **Unsubscribe (현재 구독)** | 가격 데이터 풀, 재무 없음 |
| EOD+Intraday — All World Extended | $29.99 | Upgrade | EOD + Intraday + Websocket 실시간 |
| Fundamentals Data Feed | $59.99 | Pay | 재무 전용, 라이브 가격 없음 |
| ALL-IN-ONE Package | $99.99 (Value $160) | Upgrade | 전부 포함 |

범례: ✅ = 제공 · ❌ = 미제공 · ⚙️ = 조건부(By request 등)

---

## 한도 (Limits)

| 항목 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| API Calls per Day | 20/day | **100,000/day** | 100,000/day | 100,000/day | 100,000/day |
| API Requests per Minute | 20/day | **1,000/min** | 1,000/min | 1,000/min | 1,000/min |
| Welcome Bonus API Calls | 500 | **500** | 500 | 500 | 500 |
| Additional API Calls | Upgrade | **By request** | By request | By request | By request |
| Data Range | Past year | **30+ years** | 30+ years | 30+ years | 30+ years |
| Type of Usage | Personal | **Personal** | Personal | Personal | Personal |

---

## AI & Developer Tools

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| EODHD ChatGPT Assistant | ✅ | **✅** | ✅ | ✅ | ✅ |
| MCP Server | ✅ | **✅** | ✅ | ✅ | ✅ |

---

## Stocks, ETF, Funds Data

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| US and Worldwide exchange | ✅ | **✅** | ✅ | ✅ | ✅ |
| Fundamental Data | ❌ | **❌** | ❌ | ✅ | ✅ |
| Live Data (15min Delayed) API | ✅ | **✅** | ✅ | ❌ | ✅ |
| Live data: US Extended API | ✅ | **✅** | ✅ | ❌ | ✅ |
| End Of Day | ✅ | **✅** | ✅ | ❌ | ✅ |
| Splits and Dividends | ✅ | **✅** | ✅ | ❌ | ✅ |
| Adjusted Data | ✅ | **✅** | ✅ | ❌ | ✅ |
| Delisted Data | ✅ | **✅** | ✅ | ✅ | ✅ |

---

## Forex and Cryptocurrencies

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| Live (Delayed 1 minute) API | ✅ | **✅** | ✅ | ❌ | ✅ |
| End Of Day | ✅ | **✅** | ✅ | ❌ | ✅ |

---

## Real-Time API via Websockets

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| US Stocks | ❌ | **❌** | ✅ | ❌ | ✅ |
| FOREX pairs | ❌ | **❌** | ✅ | ❌ | ✅ |
| Cryptocurrencies | ❌ | **❌** | ✅ | ❌ | ✅ |
| Simultaneous tickers | ❌ | **❌** | 50 | ❌ | 50 |

---

## Extended Data

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| Search API | ✅ | **✅** | ✅ | ✅ | ✅ |
| Technical API | ❌ | **❌** | ✅ | ❌ | ✅ |
| Intraday API | ❌ | **❌** | ✅ | ❌ | ✅ |
| Screener API | ❌ | **❌** | ✅ | ❌ | ✅ |
| US Ticks API | ❌ | **❌** | ⚙️ By request | ❌ | ✅ |

---

## Exchanges Data

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| List of supported exchanges | ✅ | **✅** | ✅ | ✅ | ✅ |
| List of traded tickers | ✅ | **✅** | ✅ | ✅ | ✅ |
| Exchange Trading Hours | ❌ | **❌** | ✅ | ❌ | ✅ |

---

## Fundamental Data (전부 우리 플랜 ❌)

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| Stock Fundamentals | ❌ | **❌** | ❌ | ✅ | ✅ |
| ETF Fundamentals | ❌ | **❌** | ❌ | ✅ | ✅ |
| Mutual Funds Fundamentals | ❌ | **❌** | ❌ | ✅ | ✅ |
| Earnings Per Share | ❌ | **❌** | ❌ | ✅ | ✅ |
| Insider Transactions | ❌ | **❌** | ❌ | ✅ | ✅ |
| Economic Events Data API | ❌ | **❌** | ❌ | ✅ | ✅ |
| Macroeconomic Data API | ❌ | **❌** | ❌ | ✅ | ✅ |
| 40,000 stock market logos | ❌ | **❌** | ❌ | ✅ | ✅ |

---

## Additional Packages

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| Corporate Events Calendar API | ❌ | **❌** | ❌ | ✅ | ✅ |
| Financial News Feed API | ✅ | **✅** | ✅ | ✅ | ✅ |
| Extended Fundamentals | ❌ | **❌** | ❌ | ⚙️ By request | ⚙️ By request |

---

## Support

| 기능 | Free | **EOD Hist (우리)** | EOD+Intraday | Fundamentals | ALL-IN-ONE |
|---|---|---|---|---|---|
| Support by webchat/email | ✅ | **✅** | ✅ | ✅ | ✅ |
| Priority Support | ❌ | **❌** | ✅ | ✅ | ✅ |

---

## 개발 시 판단 기준 (우리 = EOD Historical $19.99)

| 우리가 하려는 것 | 가능? | 비고 |
|---|---|---|
| 미국 일봉(OHLCV) 30년+ 수집 | ✅ | End Of Day + Data Range 30+ years |
| 수정주가 통일 | ✅ | Adjusted Data |
| 폐지종목 포함(생존편향 회피) | ✅ | Delisted Data |
| 분할/배당 보정 | ✅ | Splits and Dividends |
| 종목 검색·거래소/티커 목록 | ✅ | Search API + Exchanges Data |
| 재무 데이터(PER/EPS/Fundamentals) | ❌ | EODHD 미제공 → **SEC EDGAR 직접 파싱**으로 충당 |
| 분봉(Intraday) | ❌ | EOD+Intraday($29.99) 이상 필요 |
| 실시간 Websocket | ❌ | EOD+Intraday 이상 필요 |
| 기술적 지표 API / Screener | ❌ | EOD+Intraday 이상 또는 직접 계산 |

> **결론**: 우리 플랜은 **가격 기반 백테스트/랭킹에 필요한 일봉·수정주가·폐지종목·분할배당을 전부 커버**.
> 재무는 EODHD가 아니라 SEC EDGAR가 담당(분업). 분봉·실시간·재무 API가 필요해지면 그때 상위 플랜 검토.
