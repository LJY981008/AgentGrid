# 2026-06-17 EDGAR cik resolver — 현재 스냅샷 (#2)

- **유형**: 일반 구현 (플랜모드 승인)
- **관련 기획/이슈**: ADR-002 CIK 안정식별자. EODHD 가 cik 미제공 → SEC EDGAR 로 현재 ticker→cik 매핑
- **시작 시점 커밋**: `545ae91` → **완료 커밋**: 이 커밋(문서 동기화). 구현 `47314d3`(data/edgar+명세)·`5070f50`(resolver)·`ff1326c`(deps/routes enrich)·`476b957`(demo/compose).

## 의도 (Why)

종목 안정키 = CIK(영구·무재사용, 생존편향 방어). 현재 `TopEntry.cik=""`·백테스트 `StubIdentityResolver`.
SEC EDGAR `company_tickers.json`(무료·키없음·User-Agent만)로 현재 ticker→cik 적재·저장 + `IdentityResolver`
실전 구현(`EdgarSnapshotResolver`)으로 Stub 교체. ⚠️ 골격엔 cik 기능적 불필요(1년·재사용0) — 가치는
현재 cik 표시 + 결제 후 `TickerHistoryResolver`(시점별)의 기반. Protocol 영구·구현만 교체(DI).

## 계획 (승인 플랜 백업)

브레인스토밍 확정: 범위=현재 스냅샷(ticker_history 후속) / fetch=적재→저장→읽기(런타임 SEC 0·오프라인) /
ranking cik enrich=함(api 층) / 저장=JSON.

Phase0 ⚠️ api-spec BLOCKING: tech-researcher가 `docs/apis/sec-edgar/` 캡처(company_tickers.json
엔드포인트·응답 `{idx:{cik_str,ticker,title}}`·User-Agent 필수·rate limit) 선행.

파일: `data/edgar.py`(fetch_company_tickers·store/load·`__main__`, 저장=`base_dir/edgar/ticker_cik.json`
영속) · `backtest/identity.py`(EdgarSnapshotResolver — load 1회·`cik_for`→map.get(upper,"")·on무시) ·
`api/deps.py`(@lru_cache get_identity_resolver) · `compose.yaml`(EDGAR_IDENTITY interpolation) ·
api/routes/backtest(Stub→Depends) · ranking(cik enrich) · demo 전환 · 테스트(httpx 모킹·tiingo/eodhd 패턴).

graceful: 파일없음→빈맵→cik="" 폴백 / 미해소 ticker→"" / 커버리지=SEC 신고사만(ETF·외국주 미수록).
cik 채워도 meta.validated=false 불변(§4.1 — cik는 식별자지 검증 아님).

## Before — 수행 전 실측

- `TopEntry.cik=""` 하드코딩(`rules/ranking.py:157` — EODHD 미제공). `/api/ranking` cik="".
- 백테스트(api·demo) = `StubIdentityResolver({})`(cik 미해소 → ticker 앵커).
- `src/stockpick/data/` = tiingo·eodhd·ingest·... (edgar 없음). `docs/apis/` = tiingo·eodhd (sec-edgar 없음).
- edgartools 미설치(cik엔 불필요 — company_tickers.json 정적 JSON·httpx). `.env` 에 EDGAR_IDENTITY 세팅됨.
- 테스트 178 passed.

## After — 수행 후 실측

- **검증**: `ruff`·`ruff format`·`mypy`(strict 67 src) OK · `pytest` **195 passed**(178→195, +17: edgar 10 + resolver 5 + ranking-cik api 2). 훅 38. 라이브 0(httpx 모킹·tiingo/eodhd 패턴).
- **명세 캡처**(Phase0): tech-researcher → `docs/apis/sec-edgar/{company-tickers.json,_index.json}`(실측 샘플 NVDA 1045810·AAPL 320193·403 실증·User-Agent 형식·10req/s·커버리지 한계).
- **라이브 end-to-end**: `docker compose exec app python -m stockpick.data.edgar` → SEC 실 fetch **10,414건** ticker→cik 저장(User-Agent 통과·403 없음). app 재시작 후 `/api/ranking?group=all` → 실 CIK 채워짐: GOOGL `0001652044`·XOM `0000034088`·JNJ `0000200406`·NVDA `0001045810`·AAPL `0000320193` (5/5 해소). `meta.validated=false` 불변(§4.1 — cik는 식별자지 검증 아님).
- **변경 규모**: 15 files, +628/−9. 신규 `data/edgar.py`·`backtest/identity.py`·`docs/apis/sec-edgar/`·테스트 2.
- **완료 커밋**: `47314d3`(data/edgar+명세) → `5070f50`(EdgarSnapshotResolver) → `ff1326c`(deps/routes enrich·Stub 교체) → `476b957`(demo/compose) → 이 커밋(api-spec·HOME·CLAUDE 동기화).

## 비교/회고

- **의도 대비 달성도**: 100% — 현재 ticker→cik 적재→저장→읽기 + IdentityResolver 실전(EdgarSnapshotResolver)·Stub 교체·ranking/backtest cik enrich. 라이브 10,414건 해소·`/api/ranking` 실 CIK 표시 확인. EDGAR_IDENTITY 첫 사용처.
- **계획대로**: 적재→저장→읽기(런타임 SEC 0)·Protocol 영구(스냅샷은 on 무시)·graceful(저장본 없으면 cik="")·api-spec 명세 선행. 추측 0(샘플·403·rate 전부 실측).
- **남은 함정/한계**: 현재 스냅샷만(폐지·과거 ticker 미수록 — 생존편향 소스 아님) · SEC 신고사만(ETF·외국주 미해소"") · `_resolver_for` lru_cache는 base_dir별(저장본 갱신 시 app 재시작 필요 — 라이브 검증서 실측).
- **후속**: [ ] `TickerHistoryResolver`(시점별 ticker↔cik·생존편향 정답·SEC submissions) · [ ] EDGAR 재무층(XBRL·edgartools·companyfacts) · [ ] validated=true(결제+S6) · [ ] #5 benchmark/engine 루프 공유 헬퍼
