# 2026-06-17 백테스트 API 노출 + webapp BacktestPage 교체 (#4)

- **유형**: 일반 구현 (플랜모드 승인)
- **관련 기획/이슈**: M2 백테스트 엔진 후속 — 엔진을 HTTP·UI로 노출. 결제·신규키 0(무료 골격)
- **시작 시점 커밋**: `c106981` → **완료 커밋**: 이 작업 마지막 커밋(완료 시 기입)

## 의도 (Why)

M2 백테스트 엔진(`backtest/` 14모듈)은 구현됐으나 HTTP·UI 미노출 — `BacktestPage.tsx` placeholder.
엔진을 `GET /api/backtest`로 노출 + BacktestPage를 실제 결과(자산곡선·지표·벤치·미검증경고)로 교체.
⚠️ 산출은 골격·미검증 → `meta.validated=false`+경고 상시(§4.1). validated=true(결제+S6)는 범위 밖.

## 계획 (승인된 플랜 백업)

브레인스토밍 확정: ①UI=소수 컨트롤(전략·top_n·리밸주기, 서버 재계산) ②차트=Recharts(webapp-conventions
사전승인) ③v1=단일 백테스트만(walk-forward·decay UI 후속).

파일: `adapters.PriceDerivedUniverse`(신설, demo도 전환·FakeUniversePort smell 제거) · `api/models.py`
(BacktestResponse 계약) · `api/routes/backtest.py`(신규, ranking route 미러) · `api/app.py`(등록) ·
`tests/test_api.py`(백테스트 케이스) · webapp `{types,endpoints}.ts`·`BacktestPage.tsx`(교체)·`package.json`
(recharts) · `webapp-conventions.md`(차트 규약 갱신).

API: `GET /api/backtest` 쿼리 strategy·top_n·rebalance_freq(나머지 서버 고정·과적합 노브 최소화).
조합 = ParquetPriceSeriesPort→PriceDerivedUniverse→StubIdentityResolver→strategy→BacktestConfig→
engine.run→equal_weight_universe 벤치→attach_benchmarks. 응답=equity_curve·benchmark_curve·metrics·
benchmark_returns·meta(validated=false+warning+data_caveats). 빈데이터→200+경고(ranking 선례).

재사용: engine.run·benchmark·config·strategy·adapters / ranking.py 패턴 / DashboardPage·UnvalidatedWarning.

## Before — 수행 전 실측

- `webapp/src/pages/BacktestPage.tsx` = placeholder("준비 중 — 다음 마일스톤").
- `src/stockpick/api/routes/` = health·dataset·ingest·ranking·learning (backtest 없음).
- `src/stockpick/backtest/demo.py` = `_derive_universe`가 `FakeUniversePort`(테스트 픽스처) 사용 — 리뷰 smell.
- webapp 차트 = CSS 막대만(recharts 미설치).
- 테스트: 173 passed.

## After — 수행 후 실측 (완료 시 기입)

> **진행중** — 6단계 완료 시 채움.

- 검증: (ruff·mypy·pytest + webapp build + /api/backtest 스모크)
- 변경 규모: (diff stat)
- 커밋: (SHA)

## 비교/회고 (완료 시 기입)

> **진행중**

- 의도 대비 달성도:
- 후속: [ ] walk-forward UI · [ ] 파라미터 전체폼 · [ ] EDGAR cik(#2) · [ ] validated=true(결제+S6)
