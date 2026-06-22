# 2026-06-22 S6-a — full_series OOM 수정 (라이브 백테스트 50,184 가능케)

- **유형**: 플랜모드 승인
- **관련 기획/이슈**: S6(데이터 신뢰성 게이트) **1순위 선결**. [[2026-06-22-S5c후처리수정-S5d-실UniversePort]] 후속(라이브 검증이 full_series OOM에 막힌 것 해소). 사용자 확정: S6 단계분해(S6-a full_series 수정 → S6-b 게이트 별도)·임계 데이터 기반.
- **시작 시점 커밋**: `efdeade` → **완료 커밋**: (완료 시 기입, Task5 마지막)

## 의도/목적 — 왜 이 작업을 하나

S5-d 가 `MasterUniverse`(생존편향 유니버스)를 배선했으나 라이브 `/api/backtest` 가 **`full_series()` 전구간 메모리 로드(50,184 ticker × ~30년 = ~378M PricePoint)에서 OOMKilled**(mem_limit 12g) — MasterUniverse 도달 전 사망. 즉 50,184·5.1G 실데이터로 백테스트를 **한 번도 못 돌림**. S6 신뢰성 게이트(validated=true)는 라이브 백테스트가 돌아야 의미 → 이 OOM 수정이 S6 전체의 선결.

엔진이 실제 필요한 것은 **보유종목 × [entry,exit] 평가구간**(engine `_holding_period_return` 이 `full.get(ticker)` for weights)뿐인데 전체 50k×30년을 메모리에 올리는 게 결함. `trading_days()`·`load_range`·`load(as_of)` 를 DuckDB 집계/구간/윈도우 로드로 바꿔 메모리 절감하되 **백테스트 결과는 불변**(메모리 최적화가 룰 결과 바꾸면 안 됨). ⚠️ `meta.validated=false` 불변(전환은 S6-b).

## 계획 (승인 플랜 백업)

**전문**: `.claude/plans/pro-3-5-twinkling-adleman.md` (승인본).

**핵심 5 Task**(Task별 구현→리뷰 2종[convention-reviewer + code-reviewer]→게이트→커밋):
1. work-history 백업(이 문서).
2. `trading_days()` DuckDB 직접 집계(`_scan.load_trading_days`·full_series 비의존·Protocol 불변).
3. `load_range`·`load_window` 신규(`_scan`·ports·adapters·fakes) + `= ANY($tickers)` spike.
4. engine·benchmark 전환(full_series→load_range·load(as_of)→load_window·tradable 푸시필터) + **결과 불변 회귀**(실 Parquet 갭·폐지경계).
5. 라이브 측정(peak mem<12g + wall-clock) + 문서 + 이 문서 After.

**critic 검증 반영**(REVISE 2C+3M+Minor 전부 선반영):
- C1(BLOCKING narrow): `load_range`=full_series 부분집합이나 **bit-identical 아님** — 보유종목 첫봉이 exit 초과(갭)면 full은 `ret=0`(skip 아님)·load_range는 `n_skipped++`. **수익기여 양쪽 0 동일(equity 불변)**, skip 카운터만 발산 → STOP 기준 = equity/지표/n_delisted 동일, n_skipped 차이는 사유 인지·갭 회귀로 현상 고정.
- C2(성능): 리밸 ~360회 × 풀스캔(ticker=파일명·파티션 아님→프루닝 안 됨)·per-call connect 는 비현실적 느림 → wall-clock 기준 + connection 재사용.
- M3(in-scope 승격): `load(as_of=t)`가 진짜 OOM 주범(매 리밸·t 최근이면 거의 full)·측정 자체가 OOM → 조건부 아니라 **load_window in-scope**(랭킹 lookback 윈도우·상한 ≤as_of 룩어헤드 유지·tradable 푸시필터).
- M4: 회귀가 Fake만·실 DuckDB는 gapless 데모만 → 실 Parquet 회귀(갭·폐지경계·BETWEEN inclusivity).
- M5: `= ANY($tickers)` 전례 0 → Task3 spike(실 Parquet·빈 리스트).
- Minor: `PriceDerivedUniverse.full_series`(adapters.py:63) 폴백 OOM 경로 — 라이브는 스냅샷 존재로 MasterUniverse 선택(회피)·Task5 로그 확인.

## Before — 수행 전 실측 (HEAD `efdeade`)

- **라이브 `/api/backtest`(50,184·5.1G) = OOMKilled**(S5-d Task5 실측). 경로: `backtest.py:80 trading_days()` → `adapters.py:46` `sorted({... full_series().values() ...})` → `full_series()`(adapters.py:41) = `_scan.load_adjusted_series(as_of=None)`(`_scan.py:78`·`_SQL_SERIES_ALL` 전체 fetchall) → ~378M PricePoint → 12g 초과.
- `engine.py`: `full = price_port.full_series()`(50)·`load(as_of=t)`(142·`_SQL_SERIES_AS_OF` trade_date≤t 전체 종목)·`_holding_period_return`(170-203·`full.get(ticker)` for weights·`_price_on_or_after(entry)`/`_price_before(de)`/`_price_on_or_before(exit)`). `benchmark.py`: full(43)·load(as_of)(60).
- `_scan.py`: `_FROM`(40)·`_SQL_SERIES_AS_OF`/`_SQL_SERIES_ALL`(42-48)·`load_adjusted_series`(78). `= ANY` 전례 0(스칼라 바인딩만).
- `adapters.py`: `ParquetPriceSeriesPort`(trading_days 46=full_series 의존)·`PriceDerivedUniverse.__init__`(63=full_series 호출).
- 저장 레이아웃: `daily_bar/exchange={EX}/year={YYYY}/{ticker}.parquet`(storage.py:315 — ticker=파일명·파티션 아님).
- compose `app.mem_limit:12g`. alembic head=0003. backtest 테스트 전부 green(S5-d 기준).

## After — 수행 후 실측 (Task별 누적·최종 Task5 종합)

(완료 시 기입)
- 검증 결과:
- 라이브 측정(peak mem·wall-clock):
- 변경 규모:
- 커밋:

## 비교/회고

(완료 시 기입)
- 의도 대비 달성도:
- 계획과 달라진 것 + 이유:
- 후속 작업: [ ] S6-b 신뢰성 게이트(분할≥10·폐지커버리지·민감도→validated·임계 데이터기반) [ ] full_series Protocol 제거 [ ] 증분 스케줄러
