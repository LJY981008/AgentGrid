# 2026-06-17 백테스트 API 노출 + webapp BacktestPage 교체 (#4)

- **유형**: 일반 구현 (플랜모드 승인)
- **관련 기획/이슈**: M2 백테스트 엔진 후속 — 엔진을 HTTP·UI로 노출. 결제·신규키 0(무료 골격)
- **시작 시점 커밋**: `c106981` → **완료 커밋**: 이 커밋(문서 동기화). 구현 `83c163e`(PriceDerivedUniverse)·`89017df`(/api/backtest)·`f8ccb6c`(webapp BacktestPage).

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

## After — 수행 후 실측

- **검증**: `ruff check`·`ruff format --check`·`mypy`(strict 63 src) OK · `pytest` **178 passed**(173→178, +5: PriceDerivedUniverse 1 + backtest api 4[synthetic·empty·score_weight·422]). 훅 회귀 38 PASS. webapp `npm run build`(tsc strict + vite + PWA generateSW) OK.
- **라이브 스모크**(`GET /api/backtest?top_n=5`, 실데이터 9종목): validated=false·곡선 14점·총수익 0.2888·Sharpe 2.645·MDD −0.0276·벤치(등가중) 0.33 → **룰 초과수익 −0.0413(언더퍼폼)**·caveats 노출.
- **화면 검증**(playwright, http://localhost:5174/backtest): 미검증 경고 배너·전략/리밸 토글·Recharts 자산곡선(전략 vs 등가중 벤치 오버레이)·지표 그리드·미검증 한계 리스트 정상 렌더. **0 콘솔 에러.** 전략 곡선이 벤치 아래 = §4.1 정직 입증.
- **변경 규모**: 14 files, +1014/−42. recharts ^3.8.1 도입(React19 호환·peer ok).
- **완료 커밋**: `83c163e`(PriceDerivedUniverse·demo smell 제거) → `89017df`(/api/backtest) → `f8ccb6c`(webapp BacktestPage·Recharts) → 이 커밋(webapp-conventions 동기화·work-history).

## 비교/회고

- **의도 대비 달성도**: 100% — 엔진을 HTTP·UI로 노출, BacktestPage placeholder 교체 완료. 결제·신규키 0(무료 골격). meta.validated=false+경고 상시·data_caveats 노출로 §4.1 정직성 유지(화면이 룰의 벤치 언더퍼폼을 그대로 보여줌).
- **계획과 달라진 것**: ①`PriceDerivedUniverse`를 adapters에 신설해 demo의 `FakeUniversePort` smell 제거(리뷰 지적 반영 — 가격기반 유니버스는 정직한 골격 차선, 테스트용 FakeUniversePort와 분리). ②Recharts Tooltip formatter 타입(ValueType) — param을 unknown으로(contravariance) tsc strict 통과. ③recharts 버전 추측 금지 — npm view로 3.8.1·React19 peer 확인 후 핀.
- **남은 함정/한계**: 골격 유니버스=가격기반(survivorship 미보정)·cik 미해소·recharts 청크>500KB(코드스플릿 후속 여지). 전부 data_caveats·conventions에 기록.
- **후속**: [ ] walk-forward·decay UI · [ ] 파라미터 전체폼 · [ ] EDGAR cik(#2) · [ ] benchmark/engine 루프 공유 헬퍼(#5) · [ ] S6 게이트 후 validated=true(결제) · [ ] recharts 청크 코드스플릿
