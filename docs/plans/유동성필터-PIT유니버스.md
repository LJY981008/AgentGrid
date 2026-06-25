# PIT 유동성/가격 하한 유니버스 필터 — 설계 (2026-06-25)

> S6-b 게이트 2차 폭발(microcap penny + cap·복리) 해소. A1p2(sentinel 정제)의 successor.
> 상태: **설계 승인 대기**(brainstorming). 승인 후 writing-plans → 구현.

## 1. 문제 / 왜 (Context)

A1p2 로 EODHD `$1M sentinel` 핵폭발은 72자릿수 제거(worst_oos_excess −10^80 → −47). 그러나 게이트 재실행(2026-06-25) 결과 **2차 폭발 잔존** — oos_excesses 양수측 e7(fold8=8.5e7)·decay>1 폴드 7/10·G-6 비용불변. 적대검증 워크플로우 결론:

- **FAIL 은 "momentum 무알파"가 아니라 "측정 척도 오염 → robustness 미측정"**. O(1) 측정가능 폴드 단 2개(10개 중).
- **원인(둘 다)**: 잔존 **microcap penny 진입가**($0.0001·non-sentinel 실데이터·분모붕괴 **트리거**) + per-bar +19 cap × top-5 집중 × 다년 복리(**증폭기**).

→ **실투자 가능 종목만**으로 유니버스를 좁혀 분모붕괴를 근본 제거한다. 목표 = **게이트 통과가 아니라 excess 분포가 O(1) magnitude 로 수렴**(그때서야 momentum 진짜 판정 가능). 상세 finding = `.claude` 메모리 `finding-cap-compounding-explosion`.

## 2. 확정 결정 (사용자 승인)

| 항목 | 결정 | 근거 |
|---|---|---|
| 범위 | **가격 하한 + ADV 유동성**(현실적) | 가격-only 는 corner-cut·penny 만 제거. 비유동 microcap 도 배제해야 현실 |
| 가격 하한 | **raw close(t) ≥ $5** | SEC penny stock 정의·기관 보유 하한. 명목가라 분할 우량주 오제거 0 |
| 유동성 하한 | **ADV20(t) ≥ $1,000,000** | 1인 포트 충분·하위 ~60% 비유동 꼬리 제거(실측 분위수 p50=$172k·p75=$4.1M) |
| 적용 대칭 | 전략 유니버스 **AND** 벤치(equal_weight_universe) 둘 다 동일 필터 | excess = liquid-momentum vs liquid-등가중. 한쪽만 필터=비교 왜곡 |
| 멤버십 | **시점별**(t 마다 진입/이탈) | per-ticker 영구제외 아님 = 생존편향 안전 |

**임계 $5·$1M·window 20 = 데이터(게이트결과) 보기 전 동결**(과적합 BLOCKING). 게이트 통과율 보고 조정 금지.

## 3. 데이터 타당성 (실측 2026-06-25·2M 표본)

- `volume` **100% non-null**(0 null·zero-volume 봉 20.6%=거래정지/비거래일→ADV 자연 배제). `value`(달러거래대금) 는 100% NULL → 미사용, **dollar volume = raw close × volume** 로 산출.
- cache.duckdb 현재 컬럼 = `ticker·trade_date·close·adj_factor` (**volume 없음** → 재빌드 필요).

## 4. 설계

### 4.1 Config (frozen·env-tunable·재현성)
`BacktestConfig` 신규 필드(전부 fingerprint **AND** `compute_rule_signature` 포함 — 유니버스를 바꿔 validated 룰 정체성을 바꾸므로·period_return_cap 동류):
- `min_price_floor: Decimal = $5` (env `STOCKPICK_MIN_PRICE`)
- `min_adv_dollar: Decimal = $1_000_000` (env `STOCKPICK_MIN_ADV`)
- `adv_window_days: int = 20` (env `STOCKPICK_ADV_WINDOW`)
- `__post_init__`: 전부 > 0 검증(잘못된 임계 조용한 통과 금지).

### 4.2 LiquidityPort (신규 Protocol·ports.py)
```
liquid_tickers(as_of: date, candidates: set[str], *,
               min_price: Decimal, min_adv: Decimal, window: int) -> set[str]
```
- 각 후보 ticker: trade_date ≤ as_of 의 **최근 `window` 거래일** 봉으로 ADV = mean(close×volume), 최근 close.
- 반환 = `close(최근≤t) ≥ min_price AND ADV ≥ min_adv` 인 ticker 집합.
- **봉 < window 개**(신규상장 등)면 유동성 평가 불가 → **제외**(보수·조용한 추측 금지).
- 구현 2종: `DuckDBLiquidityPort`(cache.duckdb·volume 추가·PRAGMA disable_progress_bar) + `FakeLiquidityPort`(테스트).

### 4.3 cache.duckdb 재빌드
`build_cache` SELECT 에 `volume` 추가(`ticker·trade_date·close·adj_factor·volume`). 정제 데이터로 재빌드(A1p2-6 의 98.24M행). bit-identical momentum 경로 불변(close·adj_factor 그대로).

### 4.4 삽입점
engine `_rank_at`·benchmark 의 `tradable = constituents(as_of=t)` 직후:
```
tradable = universe_port.constituents(as_of=t)
tradable &= liquidity_port.liquid_tickers(as_of=t, candidates=tradable,
              min_price=config.min_price_floor, min_adv=config.min_adv_dollar,
              window=config.adv_window_days)
```
engine·benchmark **공유**(대칭). `s6_gate`·`adapters._select_*`·DI(deps) 에 liquidity_port 배선. canonical_gate_config 가 동결 임계 주입.

## 5. 가드 (BLOCKING)

- **룩어헤드**: ADV window·close 전부 `trade_date ≤ as_of`. t 결정에 t 이후 0봉. (momentum lookback 과 동일 규율.)
- **생존편향**: 시점별 멤버십(t 마다 재평가). 비유동→t 제외, 후일 유동→t' 포함. per-bar/시점·per-ticker 영구제외 아님. 폐지종목도 유동했던 기간엔 포함.
- **과적합**: $5·$1M·20 동결(SEC/기관 관행). 게이트결과 보고 조정 금지. 동결 우회는 rule_signature 불일치로 flip 차단.
- **결과 결정성**: ADV=DECIMAL(close)×int(volume) 합/개수. bit-identical 재현. PRAGMA disable_progress_bar(로그 노이즈·관측).

## 6. 재실행 목표 (성공 기준)

필터 구현 → cache volume 재빌드 → 게이트 재실행 → **oos_excesses 가 O(1) magnitude(예: |excess| < ~10)로 수렴**·decay 분포 정상화(>1 폴드 급감). 그때 G-2/G-3 가 momentum 진짜 판정. ⚠️ **수렴이 목표지 통과가 목표 아님**. 여전히 e3+ 폭발이면 → cap per-period→로그/기하(범위 밖·조건부 후속).

## 6b. 리스크 / 상호작용 (자기검토)

- **G-5(폐지커버≥30%) 상호작용**: 비유동 microcap 은 폐지 직전 거래정지가 많아, 필터가 delisted 비율을 낮출 수 있다(현재 62.9%). 단 **유동했던 기간엔 폐지종목도 포함**(시점별)이라 급락은 아닐 것. ⚠️ G-5 임계는 **동결**(필터 통과시키려 G-5 낮추기 금지) — 30% 밑이면 정직히 fail 노출(유동 유니버스의 생존편향 한계 finding). 재실행 후 delisted_ratio 실측 관찰.
- **signature 변경**: config 3필드 추가 → rule_signature·fingerprint 변경. 현 `s6_gate_result.json`(validated=false) 는 stale(불일치) — 재실행이 새 signature 로 갱신(정상·의도).
- **유니버스 축소량**: $1M ADV 가 하위 ~60% 봉 제거 → liquid 유니버스가 충분히 큰지(top-5 후보·등가중 벤치 모수) 재실행서 확인. 과축소면 임계 재검(단 동결 원칙 — 별도 사유 기록 후).
- **라이브 ranking 일관성**: api ranking 도 동일 liquidity_port 적용해야 게이트가 검증한 유니버스와 일치(flip 정합). deps DI 배선 필수.

## 7. 테스트 (TDD)

- `liquid_tickers`: 가격<$5 제외·ADV<$1M 제외·둘 다 충족 포함·window 부족 제외.
- **PIT 경계**: as_of 이후 봉이 결과 불변(룩어헤드 회귀)·as_of 당일 포함.
- **생존편향**: 같은 ticker 가 t1 비유동(제외)·t2 유동(포함) — 시점별 재평가 봉인.
- **대칭**: engine·benchmark 동일 필터 적용(벤치만 누락 시 excess 비대칭 회귀).
- **fingerprint/rule_signature**: 임계 다르면 다른 해시·동결값 매칭.
- `__post_init__`: 임계 ≤0 ValueError.
- cache 재빌드: volume 컬럼 존재·momentum bit-identical 불변.

## 8. 파일 구조

| 경로 | 변경 |
|---|---|
| `backtest/config.py` | min_price_floor·min_adv_dollar·adv_window_days(frozen·fingerprint) |
| `backtest/ports.py` | `LiquidityPort` Protocol |
| `backtest/adapters.py` | `DuckDBLiquidityPort`(cache+volume·ADV SQL) |
| `backtest/fakes.py` | `FakeLiquidityPort` |
| `backtest/engine.py`·`benchmark.py` | `_rank_at`/벤치 tradable ∩ liquid(t)·대칭 |
| `backtest/s6_gate.py` | compute_rule_signature 3필드 추가·canonical_gate_config 동결주입·CLI 배선 |
| `data/duckdb_cache.py` | build_cache SELECT 에 volume |
| `api/deps.py`·routes | liquidity_port DI(라이브 ranking 도 동일 유니버스) |
| `tests/*` | TDD 전 항목 |
| `docs/decisions/ADR-010-*` | 유동성 필터·임계 동결 결정(Task0) |

## 9. 범위 밖 (조건부 후속)
- return_cap per-period→로그/기하 재정의(1순위[이 필터] 후 잔존 e3+ 일 때만).
- 거래비용 microcap 슬리피지 현실화·winsorize(과적합 위험·비권장).
