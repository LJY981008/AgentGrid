# API 명세 (환각 방지용 권위 레퍼런스)

> 외부 API의 **실제 명세를 구조화 JSON으로 캡처**해 코드가 기억·추측이 아닌 실측 스펙을 참조하도록 한다.
> 원칙: 학습데이터 불신(CLAUDE.md). API는 변하므로 **6개월 주기 재캡처** 권장. 캡처 = 워크플로우 `tiingo-spec-capture`.

## tiingo/ — Tiingo API (미국 주식 가격 소스, ADR-002)

- 캡처: 2026-06-16, **r.jina.ai 렌더 프록시** 경유(`tiingo.com/documentation/*`는 JS 렌더 SPA라 직접 WebFetch 시 `<title>`만 반환됨).
- 인증: `Authorization: Token <KEY>` **또는** `?token=<KEY>` — ⚠️ **Bearer 아님, "Token " 접두사**. 키 = `.env`의 `TIINGO_API_KEY`.
- base_url: `https://api.tiingo.com`. 응답 `format=json|csv`(CSV가 4~5배 빠름).
- rate limit: 시간당 / 일일(EST 자정 리셋) / 월 대역폭 — 분·초 단위 제한 없음. 수치는 플랜별(pricing).
- ⚠️ 심볼: 주식 클래스 구분에 점(.) 아닌 **대시(-)** (BRK-A, SPG-P-J) — 타 소스 티커 매핑 시 변환.
- ⚠️ 라이선스: Basic/Power = 개인·내부용만, **재배포 금지**(개인 투자 분석 OK). 결과물 외부 공개 시 검토.

인덱스: [`_index.json`](tiingo/_index.json). 전체 16섹션 / 34 엔드포인트.

### stockpick 핵심 (relevant_to_stockpick=true)

| 섹션 | 용도 | 핵심 |
|---|---|---|
| [end-of-day](tiingo/end-of-day.json) | **가격(파일럿 주력)** | `GET /tiingo/daily/{ticker}/prices` — raw OHLCV + `adjClose`/`adjOpen`… + `divCash`. `startDate`/`endDate`/`resampleFreq`. 원주가+adj 동시 → 우리 adj_factor 모델 직결 |
| [fundamentals](tiingo/fundamentals.json) | 재무(참고 — 주력은 EDGAR) | 6 엔드포인트. 유료 add-on |
| [corporate-actions-dividends](tiingo/corporate-actions-dividends.json) | 배당 | 수정주가 통일 보정 |
| [corporate-actions-splits](tiingo/corporate-actions-splits.json) | 분할 | adj_factor 검증(액면분할 교차검증) |
| [utilities-search](tiingo/utilities-search.json) | 티커 검색 | 종목 탐색 |
| [general-overview](tiingo/general-overview.json) · [general-connecting](tiingo/general-connecting.json) · [general-changelog](tiingo/general-changelog.json) | 인증·연결·버전 | 위 인증/심볼/라이선스 |

### 비핵심 (참고만 — relevant_to_stockpick=false)

news · crypto · forex · iex(분봉) · mutual-fund-and-etf-fees · websockets(crypto/forex/iex). crypto·websockets-crypto·websockets-forex 3섹션은 `status=partial`(프록시 부분 확보) — 비핵심이라 보강 보류.

> 각 JSON: `endpoints[].{url_pattern, method, query_params, response_fields}` 가 코드 생성의 진실 원천. `fetch_status`·`caveats` 확인 후 사용.
