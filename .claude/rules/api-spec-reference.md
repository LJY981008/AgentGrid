---
description: External data API usage for stockpick — consult captured JSON specs under docs/apis/ as source of truth, never hallucinate endpoints/params/response fields. Loaded on data-source/adapter edits. Trigger phrases - 외부 API·어댑터·Tiingo·데이터소스 코드 작성 시.
paths: ["src/stockpick/data/**/*.py"]
---

# 외부 데이터 API 참조 규칙 — 환각 방지 (BLOCKING)

> 외부 API(Tiingo 등) 호출 코드를 쓸 때 엔드포인트·파라미터·응답 필드를 **기억·추측으로 지어내지 마라.**
> 캡처된 명세 `docs/apis/{provider}/{section}.json` 이 **유일한 진실 원천**이다.

## 사용 절차

1. 코드 전 해당 명세 JSON 을 읽는다. 인덱스: `docs/apis/{provider}/_index.json`.
2. `endpoints[].{url_pattern, method, query_params, response_fields}` 그대로 사용 — JSON 에 없는 필드/파라미터를 추가하지 마라.
3. `fetch_status` 가 `ok` 아닌 섹션(`partial`/`failed`)은 신뢰 전 재확인. `caveats` 필독.
4. 명세가 없거나 오래됨(`captured_at` 6개월+)이면 **tech-researcher 재캡처** — 워크플로우 `tiingo-spec-capture` 패턴(⚠️ `tiingo.com/documentation/*` 는 JS 렌더 SPA → `https://r.jina.ai/{url}` 렌더 프록시 경유 필수, 직접 WebFetch 는 `<title>` 만 옴).

## Tiingo (현행 가격 소스 — `docs/apis/tiingo/`)

- **인증**: `Authorization: Token <KEY>` 헤더 **또는** `?token=<KEY>` 쿼리. ⚠️ **Bearer 아님** — `"Token "` 접두사. 키 = `.env` 의 `TIINGO_API_KEY`(코드에 하드코딩·로깅 금지 — logging-rules).
- **base**: `https://api.tiingo.com`. 포맷 `format=json|csv`(CSV 4~5배 빠름).
- **가격(EOD)**: `GET /tiingo/daily/{ticker}/prices` — `startDate`·`endDate`·`resampleFreq`. 응답 raw OHLCV + `adjOpen/High/Low/Close`·`adjVolume`·`divCash` → 우리 **원주가 + adj_factor** 모델로 적재(types.DailyBar, 원본 불변).
- **심볼**: 주식 클래스 구분 **대시(-)** (BRK-A, SPG-P-J) — 점(.) 아님. EDGAR/타 소스 매핑 시 정규화.
- **rate limit**: 시간당 / 일일(EST 자정) / 월 대역폭. 분·초 제한 없음 → 체크포인트·재시도로 한도 내 운영.
- ⚠️ **재배포 금지**(Basic/Power 개인·내부용만) — 개인 분석 OK, 결과물 외부 공개 시 약관 검토.

## 금융 BLOCKING 연계

어댑터는 `DataSource` Protocol(`data/source.py`) 구현. `iter_universe(include_delisted=True)` 기본 — 무료 Tiingo 가 폐지종목 미제공이면 **조용히 누락 금지**, 한계를 호출부에 명시(생존편향). 적재는 `source`·`ingested_at` 기록(재현성). 시점 t 결정엔 `trade_date <= t` (룩어헤드). 상세 [python-conventions](python-conventions.md) §금융.
