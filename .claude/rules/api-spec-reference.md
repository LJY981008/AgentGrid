---
description: External data API usage for stockpick — consult captured JSON specs under docs/apis/ as source of truth, never hallucinate endpoints/params/response fields. Loaded on data-source/adapter edits. Trigger phrases - 외부 API·어댑터·Tiingo·EODHD·데이터소스 코드 작성 시.
paths: ["src/stockpick/data/**/*.py"]
---

# 외부 데이터 API 참조 규칙 — 환각 방지 (BLOCKING)

> 외부 API(Tiingo·EODHD 등) 호출 코드를 쓸 때 엔드포인트·파라미터·응답 필드를 **기억·추측으로 지어내지 마라.**
> 캡처된 명세 `docs/apis/{provider}/{section}.json` 이 **유일한 진실 원천**이다.

## 사용 절차

1. 코드 전 해당 명세 JSON 을 읽는다. 인덱스: `docs/apis/{provider}/_index.json`.
2. `endpoints[].{url_pattern, method, query_params, response_fields}` 그대로 사용 — JSON 에 없는 필드/파라미터를 추가하지 마라.
3. `fetch_status` 가 `ok` 아닌 섹션(`partial`/`failed`)은 신뢰 전 재확인. `caveats` 필독.
4. 명세가 없거나 오래됨(`captured_at` 6개월+)이면 **tech-researcher 재캡처** — 워크플로우 `eodhd-spec-capture`(현행 주력)·`tiingo-spec-capture` 패턴(⚠️ `tiingo.com/documentation/*`·`eodhd.com` 은 JS 렌더 SPA → `https://r.jina.ai/{url}` 렌더 프록시 경유 필수, 직접 WebFetch 는 `<title>` 만 옴).

## EODHD (M2 현행 가격 소스 — `docs/apis/eodhd/`, 62섹션/189EP)

- **인증**: `?api_token=<KEY>` **쿼리 파라미터**(⚠️ Tiingo 의 `Authorization: Token` 헤더와 다름). 키 = `.env` 의 `EODHD_API_KEY`(하드코딩·로깅 금지). DEMO 키로 일부 테스트 가능.
- **base**: `https://eodhd.com/api`.
- **가격(EOD)**: `GET /api/eod/{SYMBOL}` — raw OHLC + `adjusted_close`(split+dividend) → 우리 **원주가 + adj_factor** 모델로 적재(원본 불변). 어댑터 = `data/eodhd.py`(`EodhdSource`).
- **생존편향 핵심 섹션**: `delisted-stock-companies-data`(폐지 ~2000년부터)·`sp-dow-jones-historical-constituents`(지수 historical constituents)·`us-stock-symbol-rename-history`(티커 연속성). 유니버스는 폐지 포함 적재.
- **rate limit**: 한도·소비 모델은 `docs/apis/eodhd/api-limits.json` 이 진실 원천(유료 기본 100,000 calls/day·심볼요청 1콜·Bulk 100콜 등, 분당 1000 requests). ⚠️ 무료티어 일일 한도는 해당 페이지 미기재(별도 실측 필요) — 숫자 단정 금지.

## SEC EDGAR (ticker→cik 식별·재무 — `docs/apis/sec-edgar/`)

- **인증**: **API 키 없음**. 단 `User-Agent` 헤더에 신원(이름+이메일) 필수 — 없으면 **403**(실측). 값 = `.env` 의 `EDGAR_IDENTITY`(비밀 아님·연락처, 토큰 아님). rate limit ~10 req/s.
- **현재 ticker→cik**: `GET https://www.sec.gov/files/company_tickers.json` — 응답 `{idx:{cik_str:int, ticker, title}}`. ⚠️ 인덱스 키 비안정 → `.values()` 순회. cik 는 **10자리 zero-pad**. 어댑터 = `data/edgar.py`(fetch→`base_dir/edgar/ticker_cik.json` 저장→`EdgarSnapshotResolver` 읽기). 커버리지=SEC 신고사만(ETF·외국주 미수록 → 미해소 cik="").
- **재무(XBRL companyfacts — `docs/apis/sec-edgar/companyfacts.json` 캡처됨)**: `GET https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` — 응답 `{cik, entityName, facts:{<taxonomy>:{<Concept>:{units:{<unit>:[{end,val,filed,fy,fp,form,start?,frame?}]}}}}}`. ⚠️ **PIT=`filed`(공시일)** — `end`(회계기간말) 아님(공시 시차 → end 기준이면 미래 누설). ⚠️ NetIncomeLoss 는 연간(fp=FY/10-K)+분기(Q1~3/10-Q) **혼재** → 연간만 쓰려면 fp=='FY' 필터. concept 결측 정상. **직접 JSON 파싱**(edgartools 미사용 — [ADR-005](../../docs/decisions/ADR-005-재무-직접파싱.md)). 어댑터 = `data/edgar.fetch_companyfacts`(소수 concept: StockholdersEquity·NetIncomeLoss·EntityCommonStockSharesOutstanding)→`store_financials`→`base_dir/edgar/financials.json`. PIT 선택=`rules/_financials.latest_as_of`(disclosed_at<=as_of). 팩터=`rules/factors.financial_factors`(ROE·P/B). `__main__ financials` 는 가격 데이터셋 ticker 의 cik 만 fetch(전체 아님·10req/s).
- ⚠️ '현재' 매핑만 — 폐지·과거 ticker 미수록(생존편향 소스 아님). 시점별 ticker_history 는 후속. submissions 엔드포인트는 미사용.

## Tiingo (M1 파일럿 가격 소스 — `docs/apis/tiingo/`)

- **인증**: `Authorization: Token <KEY>` 헤더 **또는** `?token=<KEY>` 쿼리. ⚠️ **Bearer 아님** — `"Token "` 접두사. 키 = `.env` 의 `TIINGO_API_KEY`(코드에 하드코딩·로깅 금지 — logging-rules).
- **base**: `https://api.tiingo.com`. 포맷 `format=json|csv`(CSV 4~5배 빠름).
- **가격(EOD)**: `GET /tiingo/daily/{ticker}/prices` — `startDate`·`endDate`·`resampleFreq`. 응답 raw OHLCV + `adjOpen/High/Low/Close`·`adjVolume`·`divCash` → 우리 **원주가 + adj_factor** 모델로 적재(types.DailyBar, 원본 불변).
- **심볼**: 주식 클래스 구분 **대시(-)** (BRK-A, SPG-P-J) — 점(.) 아님. EDGAR/타 소스 매핑 시 정규화.
- **rate limit**: 시간당 / 일일(EST 자정) / 월 대역폭. 분·초 제한 없음 → 체크포인트·재시도로 한도 내 운영.
- ⚠️ **재배포 금지**(Basic/Power 개인·내부용만) — 개인 분석 OK, 결과물 외부 공개 시 약관 검토.

## 금융 BLOCKING 연계

어댑터는 `DataSource` Protocol(`data/source.py`) 구현. `iter_universe(include_delisted=True)` 기본 — 무료 Tiingo 가 폐지종목 미제공이면 **조용히 누락 금지**, 한계를 호출부에 명시(생존편향). 적재는 `source`·`ingested_at` 기록(재현성). 시점 t 결정엔 `trade_date <= t` (룩어헤드). 상세 [python-conventions](python-conventions.md) §금융.
