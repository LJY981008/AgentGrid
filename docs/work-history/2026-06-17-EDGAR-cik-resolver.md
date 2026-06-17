# 2026-06-17 EDGAR cik resolver — 현재 스냅샷 (#2)

- **유형**: 일반 구현 (플랜모드 승인)
- **관련 기획/이슈**: ADR-002 CIK 안정식별자. EODHD 가 cik 미제공 → SEC EDGAR 로 현재 ticker→cik 매핑
- **시작 시점 커밋**: `545ae91` → **완료 커밋**: 이 작업 마지막 커밋(완료 시 기입)

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

## After — 수행 후 실측 (완료 시 기입)

> **진행중** — Step 0~6 완료 시 채움.

- 검증·라이브 cik·변경규모·커밋: (완료 시)

## 비교/회고 (완료 시 기입)

> **진행중**

- 의도 대비 달성도:
- 후속: [ ] TickerHistoryResolver(시점별·생존편향) · [ ] EDGAR 재무층(XBRL·edgartools) · [ ] validated=true(결제+S6)
