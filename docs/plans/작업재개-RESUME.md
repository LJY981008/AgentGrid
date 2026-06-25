# 🔄 작업 재개 플랜 (compact 생존용 — 이 문서 하나로 바로 이어가기)

## 🆕 현 위치 (2026-06-25 — **최신·이 섹션 먼저 읽어라**)

> **한 줄**: validated 판정 위해 momentum 백테스트를 **표준 퀀트 셋업으로 전면 교정**(다전문가 토의·승인). Phase 0 진단·Phase 1 동결(ADR-010)·**Phase 2 구현 6단(2-4~2-9) 전부 완료**(decile·유동성 대칭·동일비용 벤치·signature B1·R2 게이트·ranking (c)·sabotage·decile wiring smoke — 전체 TDD green·ruff/mypy clean). **다음 = 빠른경로 sanity → 게이트 1회**(둘 다 사용자 격리 실행).
>
> **🔴 게이트 전 선결(H2·실측 2026-06-25)**: `cache.duckdb`(98.2M행)에 **`volume` 컬럼 없음**(Phase 2-3 전 빌드·컬럼=ticker/trade_date/close/adj_factor). 유동성 필터가 volume 필요 → 현 cache 로 게이트 실행 시 query 크래시(또는 Noop 폴백=거짓PASS). **반드시 cache 재빌드 선행**: app 정지 후 격리 — `docker compose stop app web && docker compose run -d --rm --no-deps app python -m stockpick.data.bulk --finalize`(commit 직후 build_cache·volume 포함) 또는 직접 `build_cache(base_dir)`. 재빌드 후 위 schema 에 `volume` 확인.
>
> **읽기 순서(재개)**: 이 섹션 → 활성 플랜 `/home/code/.claude/plans/pro-3-5-twinkling-adleman.md`(Phase 0~3 전문) → [[../decisions/ADR-010-백테스트방법론-표준교정-동결]](동결 결정·근거) → `docs/work-history/2026-06-25-백테스트방법론-전면교정.md`(진행·실측·6단 커밋 SHA). roadmap 메모리 자동 recall 됨.

### 왜 이 작업 (배경)
S6-b 게이트 첫 판정 `validated=false`. **G-7 블로커(0-price)는 A-1 정제로 해소**(커밋 ec4f2b8~6b74472·verify PASS). 재실행했더니 **G-3 등 e80 폭발** → A1p2(EODHD $1M sentinel 정제·커밋 1a721fe)로 72자릿수 제거. 그래도 **2차 폭발(oos_excess e7) 잔존**. **3 전문가(미국주식 퀀트·구현·적대비판) 독립 수렴**: 폭발 근본 = microcap 아니라 **측정 셋업(증폭기)** = `top-5(w=0.2) × per-ticker +19 cap × 산술복리 × 등가중-전체 벤치`. → **유동성 필터만=band-aid**. 표준 퀀트(JT2001/CRSP/Russell)로 전면 교정해 **공정 측정** → 정직한 판정.

### 결정 동결 (ADR-010·게이트 전 pre-registration·**변경 금지·진단으로도 못 흔듦=R1 방화벽**)
| 항목 | 동결값 | 근거 |
|---|---|---|
| 기간 | **2000-01-01~2026-06-18** | 0d 실측: pre-2000 폐지 미완비=생존편향(1962=27티커·폐지 pre-1995≈0·2000=10,222) |
| 수익처리 | per-ticker simple return **clip ±100%**(`period_return_cap`=**1.0**·min(ret,cap)) | 0a 실측: +19 cap=증폭기(1 cap-hit pret +380%·×4.8). +1.0 clip=증폭기 제거 |
| 포트(검증) | **top decile**(유동 유니버스 상위 10%·가변·초기 최소 20) | 표준 momentum=decile. top-5=별도 product 변형 |
| lookback | **12-1(252/21)** 1차·126/21 변형 | JT 학술 주류 |
| 벤치 | 전략과 **동일 cost_bps** + 유동성필터 + **등가중**(시총가중 0c 불가) | M1·등가중 small-cap 틸트 caveat |
| 유니버스 | close(t)≥**$5** + ADV20≥**$1M** + 종목유형 제외. **시총하한 없음**(0c SEC shares≈0%→ADV 프록시) | JT2001·절대값 컷(NYSE decile 비채택=과설계) |
| R2 측정게이트 | **`|worst_oos_excess|≤10`**(G-3 분리) | 외부원칙·미수렴=인프라부족 정직노출 |
| G-3 | 동일비용·decile 재정의·**집계 전-fold 유지**(보수·loosening 금지) | amends ADR-009 |
| R4 | 게이트=decile 검증·운영 Top5=decile 상위 부분집합·flip signature=decile | 검증룰≠운영룰 다리 |

### 고려/봉인된 정직성 가드 (재litigate 금지)
- **R1 방화벽(critic·BLOCKING)**: 진단(0a/0c/0d)은 방법 **종류**만 결정. 수치 임계는 전부 외부 시장원칙 동결 — 진단 분포 보고 "이 값이 excess 예쁘다" 선택=p-hacking 금지.
- **pre-registration(C2)**: 방법론 ALL 동결 후 **게이트 1회**. 패치-재실행 루프=OOS 오염 금지.
- **R3**: ±100% clip이 momentum 정당 우측꼬리 죽이는지 0a로 점검(cap-hit=+1900%/월=정상 알파 아님→완화 확인).
- momentum 피벗은 **깨끗한 측정 후·fail 시에만**(지금 피벗=인프라버그를 룰 무알파로 오진). 양 전문가 ACCEPT-WITH-RESERVATIONS.

### 완료 (커밋·381 passed·mypy/ruff clean)
- Phase 0 진단(f8d2614·8994d2c)·Phase 1 ADR-010(8994d2c).
- **2-1 수익처리 root fix**(5bcb48e): cap 19→1.0. **실증**: total_return **2.2e20→−1.0**(폭발 소멸)·pret>+380% 20→0개·증폭기=root 확정.
- 2-2 유동성 config 3필드(be0cff2). 2-3 LiquidityPort+`query_liquid_tickers` SQL+cache volume(267e5ea).

### ✅ 구현 완료 (Phase 2-4~2-9·2026-06-25·전체 TDD green·6 커밋 3d1e7f6~b404425)
1. ✅ **decile 전략**(2-4·3d1e7f6): `TopDecileEqualWeight`(pct·floor)+config `portfolio_pct`/`decile_min_holdings`(fingerprint).
2. ✅ **engine/bench 유동성 대칭 배선**(2-5·811ad46): `tradable &= liquidity_port.liquid_tickers(t,tradable)` engine·벤치 대칭·decile 풀(portfolio_pct 시 전 후보→전략 decile)·`liquidity_port` 필수 kw DI(run·equal_weight_universe·walk_forward·run_s6_gate·CLI·demo·profile·api/backtest).
3. ✅ **벤치 동일비용**(2-6·811ad46): `cost_total`/`turnover_total` 0강제 해제→`_turnover`+config.cost_bps(M2 trap).
4. ✅ **s6_gate signature/canonical**(2-7·2f0bdc5): `compute_rule_signature` 5신필드(portfolio_pct·decile_min·유동성 3)+`canonical_gate_config` **decile/252·21/2000~2026 frozen**(B1 단일출처)+`ranking_rule_signature` R4(top_n 제거)+**R2 측정게이트**(|worst_oos_excess|≤10·passed AND).
5. ✅ **ranking-API (c)사후필터**(2-8·7cea0d1): `_select_liquidity_port` 선필터(rules 불변·모듈경계)+route signature 정합.
6. ✅ **sabotage 대칭 + decile wiring smoke**(2-9·b404425): engine↔bench 유동성 대칭·`run_s6_gate` decile 경로 end-to-end 실측 통과.

### ▶ 남은 작업 (사용자 격리 실행 — 게이트 전 H2 선결 필수)
0. **🔴 cache 재빌드(volume)** — 위 H2 블로커. app 정지 후 격리 build_cache. **안 하면 sanity/게이트 무효**.
1. **빠른경로 sanity**: 축소 decile config(최근~20년·2~3 fold)로 R2 excess 수렴(|excess|≤10)·decay 정상화 확인(분 단위·`docker run` 격리). decile wiring smoke 는 합성서 통과 — 실데이터 R2 수렴이 핵심 미지수.
2. **신뢰구간 게이트 1회**: `canonical_gate_config()`(decile·2000~2026)·app·web 정지·`docker run --memory 20g`·MALLOC_ARENA_MAX=2(H3) → R2 판정 → G-1~G-8 → validated 결정. ⚠️ pre-registration: 패치-재실행 루프 금지(게이트 1회).

### ⚠️ 재개 함정 (누락검증 반영·반드시 읽어라)
- **B1(BLOCKING·flip 영원히-false)**: 게이트 CLI `s6_gate.py`는 `canonical_gate_config(start=days[0], end=days[-1])` 호출 — 함수 기본값이 아직 `top_n=5·lookback126·start=days[0]`. **이 팩토리가 decile signature·R4 flip 정합의 단일 출처** → #4서 기본값을 decile비율·252/21·**2000-01-01** 동결값으로 바꿔야 CLI/route/ranking 3자 signature 일치(안 하면 검증은 decile·signature는 top5 발산→validated 영원히 false). `compute_rule_signature`에 유동성3필드 추가 시 `ranking_rule_signature`·route 동시 갱신.
- **H1(clip 표기)**: 수익처리 clip은 **상한-only `min(ret,cap)` 로 이미 충분**(ret≥−1 구조적·engine.py:236). ADR-010 표 '[−1.0,+1.0]'은 효과 동등 의미지 **하한 floor 추가 지시 아님**(floor=낙관편향·금지).
- **H2(거짓 PASS)**: 게이트 전 `cache.duckdb`+**volume 재빌드 확인 필수**. 부재 시 `_select_liquidity_port`가 `_NoopLiquidityPort`(필터 OFF·WARNING만) 반환→유동성 필터 없이 거짓 PASS. `build_cache`(volume) 선행.
- **H3(게이트 OOM)**: 격리 실행 = **`docker run --memory 20g`(별도 컨테이너)** — app mem_limit:12g 로는 native peak~13GB OOM(137). "mem_limit 임시 20g 후 복원" 가정은 미검증이니 격리 컨테이너가 안전. +MALLOC_ARENA_MAX=2.
- **M1(decile 분모)**: decile = **유동성 필터 통과 후 랭킹 후보 수**의 상위 10%(전체 유니버스 아님). floor min(20). `config.top_n`→`top_pct` 비율 신필드(fingerprint+signature 동결).
- **M2(벤치 비용)**: #3서 benchmark `cost_total=Decimal(0)` 해제 시 **`turnover_total=Decimal(0)`도 동반 해제**(둘 다 0이면 cost_bps 곱해도 0=무효). G-3 동일비용·decile 재측정.
- **L1(시작점)**: 남은작업 #1(decile)=work-history "Phase 2-4". **커밋 250b04b 이후가 시작점**.
- **L2(커밋 함정)**: 커밋 메시지 본문 `(명령어)` 괄호=verify-commit-msg 훅 subject 오파싱 차단 → `git commit -F <파일>`. **src/** 변경 커밋엔 `docs/work-history/` 엔트리 필수**(drift 훅 차단).

### 운영 메모
- 검증: `docker compose run --rm --no-deps app sh -c 'ruff check src tests && mypy && pytest -q'`.
- 진단 스크립트 패턴: scratchpad `diag_0a.py`(engine.run 1패스·equity_curve→pret 분포·결과불변). 빠른경로=직접 engine.run(축소 기간/fold).
- ⚠️ docker stop/compose stop 은 guard 미차단(prune·rm·DDL만 차단). `_old` 0-price 는 A-1서 해소.

---


> **compact된 Claude 읽는 법**: CLAUDE.md → [PLAN_STATUS](PLAN_STATUS.md) → 이 문서. 결정은 ADR(`docs/decisions/`), 데이터 스펙은 [M1-데이터파이프라인](M1-데이터파이프라인.md). 최신 갱신 **2026-06-23 ②(S6-b 신뢰성 게이트 판정=validated=false·G-7 무결성 블로커)**.
> 💡 **EODHD 무료티어 실측(2026-06-17)**: 가격 history=**최신 1년(251 거래일)만**, 과거 범위 요청은 무시. **유니버스는 무료 전체**(활성 51,705 + 폐지 57,825 = 109,530, 폐지 리스트 포함). 파이프라인 end-to-end(EodhdSource→Parquet→검증 게이트)가 무료 실데이터로 PASS. → **M2(룰·백테스트) 개발은 무료 1년치로 가능**, 전체 다년 history만 유료($19.99) 전환. 결제를 M2 끝까지 미룰 수 있음.

> **현 위치 한 줄(2026-06-23 ②)**: 미장 stockpick. M0~M3✅·전체 50,184 풀백필✅·관측성✅·**S6-b 신뢰성 게이트 구축+풀실행 완료 → 판정 `validated=false`(G-7 무결성 블로커: 0-price 542,588행·99.6% 비-_old·원인 미상)**. momentum OOS 미평가(데이터 신뢰 불가·단락). **다음 = 데이터 정제(비-_old 0-price 원인 규명)→게이트 재실행(백테스트 12g OOM·mem>12g 선결)→momentum G-1~G-6 실판정→validated 결정**(상세 ↓ "남은 순서"). ⚠️ 그 전 `meta.validated=true` 금지. ── (이력 보존) ──
> **이전 마일스톤 이력**: M0~M1 파일럿·코드리뷰 완료. **+ M2**: EODHD generic 적재(`ingest.py`, history 무관·결제후 자동확장)로 무료 1년치 9종목 데이터셋 + **룰엔진 수직슬라이스**(`src/stockpick/rules/` 모멘텀 팩터→Top 랭킹, 룩어헤드 sabotage 검증, 114 passed). Top 랭킹 라이브 동작 확인(GOOGL 38.58%·XOM 36.68% 등). **+ M3 착수·완료**(2c9ab10·b7c5b21): FastAPI API층(`src/stockpick/api/` — routes/{health,dataset,ingest,ranking,learning}로 수집·랭킹·학습 HTTP 노출, `ranking`에 `meta.validated=false` 하드코딩 §4.1 미검증 경고 상시) + webapp PWA(`webapp/` Vite8/React19, pages 5화면: Dashboard(랭킹)·Data·Universe·Learning·Backtest placeholder + 404) + compose 풀스택(postgres+app+web). **+ M2 백테스트 엔진 골격 완료**(`src/stockpick/backtest/` 14모듈·자체구현 ADR-004·룩어헤드(진입 t+1)/생존편향(UniversePort)/폐지청산 가드·CAGR/Sharpe/MDD·IS/OOS 워크포워드·purge·decay·등가중 벤치, 173 passed, 데모 9종목 13기간 동작·룰이 등가중벤치 언더퍼폼=미검증 입증). **+ M3 후속 완료**(#4·#2·#5, 푸시됨): `/api/backtest`+BacktestPage(Recharts 자산곡선·벤치·미검증경고) · EDGAR cik resolver(`data/edgar`·`EdgarSnapshotResolver`, 라이브 10,414건·`/api/ranking` 실 CIK) · 리밸 루프 공유헬퍼(`calendar.holding_periods`). 197 passed. **다음 = S6 데이터 신뢰성 게이트**(EODHD 결제 $19.99·다년·전체유니버스·실폐지) 후 백테스트 실검증 — 그 전 `meta.validated=true` 금지. 상세 백로그 ↓.
> ⚠️ **데이터셋은 컨테이너 내부 `data/parquet`만**(호스트 미마운트·gitignore) — 컨테이너 재생성 시 소실, `python -m stockpick.data.ingest` 재실행으로 복원. 룰 데모/백테스트는 `docker compose exec` 로.

## 📍 다음 작업 순서 (2026-06-22 갱신 — 사용자)

> S5 4분해: **S5-a·S5-b·S5-c·S5-d ✅ 전부 완료**. EODHD $19.99 결제(06-18). 전체 50,184 풀백필 **완주**(5.1G·OOM 1회→app `mem_limit:12g` 격리 복구). S5-c 후처리 버그(verify_parquet ≥400s가 날짜 backfill·commit 막아 PG 29/50,184만) 수정+`--finalize` 복구(날짜·snapshot 50,184).

**~~1. S5-d 실 UniversePort~~ ✅ 완료(2026-06-22)**: `MasterUniverse`(종목마스터→시점 멤버십·`delisted_at+1day` 경계변환·생존편향/룩어헤드-correct)·`export_stock_snapshot`·`_select_universe` 배선·run_bulk 후처리 재구조화(commit 호출부·C1)·`--finalize` 복구. critic REVISE 2C+3M 반영·Task별 리뷰 2종. 플랜 백업=`docs/work-history/2026-06-22-S5c후처리수정-S5d-실UniversePort.md`.

**~~2. S6-a full_series OOM + 백테스트 라이브 실용화(DuckDB)~~ ✅ 완료(2026-06-22 ②·ADR-007)**: S6-a `full_series`→`load_range`(OOM 회피). 후속 `data/duckdb_cache.py`(Parquet→`cache.duckdb` 1억49만행·1.29GB) + **momentum 부분 푸시다운**(SQL 끝점·Python Decimal·bit-identical) + `DuckDBPriceSeriesPort`(`MomentumScorePort`)·`_select_price_port`·engine `isinstance` 분기. Task0~7·리뷰 2종(Task2 결과불변 BLOCKING 버그 tot→wn 차단). 측정: **ranking 32.3×**(43.3s→1.34s·≥10×)·실데이터 18,311종목 **score 불일치 0**·풀 백테스트 774리밸 **완주**(70분·peak 12,033MB·OOM 0). 플랜 백업=`docs/work-history/2026-06-22-백테스트-라이브실용화-DuckDB컬럼스토어.md`.

**~~3. 벤치 멤버십 SQL 푸시다운~~ ✅ 완료(2026-06-23)**: `tickers_with_data`(DISTINCT ticker·load_range 키집합 동치·NULL 가드)로 3.65M PricePoint 물질화 제거. 풀 백테스트 **70→25.5분(2.7×)**·단일리밸 멤버십 10.5×·결과 bit-identical·리뷰 2종 APPROVE. 커밋 `fc4fbc6`/`8d54025`.

**~~4. 관측성 스택(Prometheus+Grafana)~~ ✅ 완료(2026-06-23·ADR-008)**: `PhaseProfile` 계측(stdlib·결과불변)+profile CLI(라이브 /metrics·**rss vs python peak 범인 가림**·Pushgateway round)+instrumentator+compose 4서비스(prometheus/grafana3001/pushgateway/profiler)+레이어 대시보드(L1신호등/L3파이프라인/L4무결성/호스트)+Local Snapshot 런북. 플랜 백업=`docs/work-history/2026-06-23-관측성-스택.md`·`observability/README.md`.

**~~5. S6-b 신뢰성 게이트~~ ✅ 구축 완료·판정=`validated=false`(2026-06-23 ②·ADR-009)**: `backtest/s6_gate.py`(G-1~G-8 **사전동결** 임계 모듈상수·`run_s6_gate`·`sensitivity_analysis`·`evaluate_criteria` 순수판정·`compute_rule_signature`/`load_s6_gate_verdict` validated flip·격리 CLI·G-7 fail 시 백테스트 단락). ranking/backtest validated 배선. Task0~5·Task별 리뷰 2종. **전구간 풀 실행 판정: G-7 무결성 FAIL**(가격<=0 **542,588행**·OHLC위반 **88,064행** — **99.6% 비-`_old` 일반티커**·원인 미상[`_old` 0.39%뿐·플레이스홀더 가설 오귀속 정정]·verify 정확). momentum OOS 강건성 **미평가**(데이터 신뢰 불가·단락). **2 실버그 수정**: verify_parquet OOM(`_VERIFY_MEMORY_LIMIT` 4GB+spill)·백테스트 12g OOM(백로그). 플랜 백업=`docs/work-history/2026-06-23-S6b-신뢰성게이트.md`·`s6_gate_result.json`.

**남은 순서** (S6-b 판정 후속 — validated=true 까지):
1. ⭐ **데이터 정제(S6-b 완료 선결)**: **0-price 542,588행**(close/open/high/low<=0)·OHLC위반 88,064행. ⚠️ **`_old` 필터 금지**(0.39%만 제거) — **비-`_old` 일반티커 504,591행(99.6%·VHAI·SWAV·HYPRQ 등·일부 epoch 1970-01-01) 원인 규명**(EODHD raw 0 적재 vs 적재/캐시 버그)이 본질. EODHD 적재 경로(`data/eodhd`·`bulk`)서 0-price **missing 처리** 또는 정제. 정제 후 verify(G-7) PASS 해야 G-1~G-6 평가 가능.
2. **백테스트 단계 메모리(게이트 재실행 선결)**: 게이트 walk_forward(3비용×10폴드 앵커드 expanding-IS)가 단일풀 11.9GB 누적으로 **12g OOM**. mem_limit>12g 격리(`docker run --memory`) 또는 백테스트 단계 메모리 최적화(peak 범인=관측성 백로그). 정제+이거 후 momentum **G-1~G-6 실판정** → validated 결정.
3. **peak ~12GB 범인 확정**(관측성 백로그): rss≫python=native(memray --temporal). 위 2번과 동류 — DuckDB cgroup 무인지(verify 는 수정·백테스트 경로 남음).
4. **full_series Protocol 제거**(+M1: DuckDB 무스냅샷 `PriceDerivedUniverse.full_series` OOM 경로)·**zero-adjusted/0-price WARNING 집계화**.
5. **증분 스케줄러**(신규 운영 마일스톤 — 아래 설계 메모):

### 증분 스케줄러 설계 메모 (캡처 명세 실측 — `docs/apis/eodhd/`)
- **패턴**: 1회 풀백필(완료 후) → 일일 증분(last_bar+1 ~ today). EOD 표준.
- **증분 효율**: per-symbol(50,184콜/일·일일한도 절반) ❌ → **`/eod-bulk-last-day/{EXCHANGE}`**(거래소 전체 1일치 1요청=100콜·`date`로 과거일 지정·`type=splits|dividends` 분기) ✅ ~6거래소×100 ≈ 600콜/일.
- ⛔ **BLOCKING — 분할/배당 소급 재조정**: `adjusted_close`는 미래 분할·배당으로 과거 전체가 소급 변동. 순수 append=과거 수정주가 stale=백테스트 오염(수정주가 통일 위반). 해결: **(권장)** 원주가 불변 저장+splits/dividends 액션테이블 별도 적재→읽을 때 adj_factor 재계산(`type=splits|dividends` 또는 per-symbol `/api/splits`·`/api/div`, 배당 `value`(수정)/`unadjustedValue`(실액) 분리). 차선: 매일 액션 발생 심볼만 full-history 재싱크. **선결: 현 저장모델이 원주가+adj_factor인지 adjusted 스냅샷인지 확인**(후자면 stale 실재).
- **폐지종목=증분 불요**(terminal). 활성만 갱신. **신규상장/재활성**=주기적 유니버스 재적재(S5-b 재실행). 증분 후 stock_snapshot.json 재export(MasterUniverse 최신화).
- **스케줄러=로컬**(cron/systemd/compose cron 서비스/in-app APScheduler) — `/schedule` 클라우드 에이전트 ❌(로컬 PG·parquet 볼륨 접근 불가).

## 확정 결정 (변경 금지 — 근거는 ADR)
- **시장**: 미국(NYSE/NASDAQ/AMEX). 한국 보류(나중 재사용 가능).
- **가격**: Tiingo(파일럿·무료)→**EODHD**(본격 $19.99/월, [ADR-003](../decisions/ADR-003-M2-가격소스-EODHD.md)). **재무**: SEC EDGAR(무료·`filed`=PIT)+edgartools ([ADR-002](../decisions/ADR-002-미국-데이터소스-아키텍처.md)).
- **결합**: 가격↔재무 `merge_asof` PIT 조인(disclosed_at≤t). **마이그레이션**: alembic ([ADR-001](../decisions/ADR-001-마이그레이션-도구-alembic.md)).
- **종목 식별**: CIK(안정·무재사용)+ticker(시변·재사용) → `ticker_history` 브리지로 재사용 생존편향 누수 차단.
- **기각**: SimFin(PIT 미충족), RabbitMQ(1인 배치 과설계), LLM 런타임 정규화(무결성), yfinance(생존편향).
- **history**: 30년 강제 아님(예시였음) — 데이터 가용범위 전부(많을수록 검증 정확도↑).
- **재현성 vs 해지-삭제 조항**: 무관(과거 EOD 불변·재구독 동일데이터 재취득). 개인·비배포 사용. 시스템에 위반 인코딩 안 함.
- **신뢰성 게이트**: M1 넓게 수집+품질꼬리표 / 표준(1%)·엄격(0.5%) 임계는 M2 민감도분석 gap(과적합 금지). **폐지 fallback**: 확보분+누락 정량고지, 커버리지 하한 미달 시 M1 차단.

## 현 코드 상태 (HEAD 기준)
- `src/stockpick/types.py`: `Exchange`(StrEnum), `Stock`(cik+ticker), `DailyBar`(ticker·Decimal OHLC·adj_factor), `TopEntry`(cik앵커). `Financial`은 EDGAR 단계 보류(주석).
- `src/stockpick/data/source.py`: `DataSource` Protocol(runtime_checkable) — `iter_universe(include_delisted=True)`·`fetch_daily_bars`.
- `src/stockpick/data/tiingo.py`: `TiingoSource` — EOD, `Authorization: Token`(Bearer아님), adj_factor=adjClose/close. 모킹 테스트 `tests/test_tiingo.py`.
- `src/stockpick/data/storage.py`: Hive Parquet(`exchange=/year=`, decimal128 정밀보존, 멱등 **ticker별 파일**, source/ingested_at) + DuckDB 검증 게이트. `tests/test_storage.py`.
- `src/stockpick/data/pilot.py`: 라이브 파일럿(`python -m stockpick.data.pilot`). `tests/test_pilot.py`.
- `src/stockpick/data/eodhd.py`: `EodhdSource(DataSource)` — `GET /api/eod/{TICKER}.{EX}`, `?api_token=` 쿼리 인증, raw OHLC+adjusted_close→adj_factor, 폐지 포함 유니버스. `tests/test_eodhd.py`.
- `src/stockpick/data/_adjust.py`: 공유 `compute_adj_factor`(adjusted/raw 12자리 quantize). `src/stockpick/data/ingest.py`: 소스무관 generic 적재(history 무관·결제후 자동확장). `tests/test_{adjust,ingest}.py`.
- `src/stockpick/rules/`: `factors.py`(모멘텀)·`ranking.py`(Top 랭킹·TopEntry)·`_scan.py`(룩어헤드 as_of 가드)·`demo.py`·`__main__.py`. `tests/test_rules.py`.
- `src/stockpick/api/`: FastAPI(`app.py`·`deps.py`·`models.py` pydantic 계약·`routes/{health,dataset,ingest,ranking,learning}.py`). `python -m stockpick.api` 기동. `tests/test_api.py`. ⚠️ ranking `meta.validated=false` 상시(백테스트 엔진은 구현됐으나 S6 미통과·골격이라 룰 미입증).
- `webapp/`: PWA(Vite8/React19/react-router7/TS) — `src/{api,components,pages}`, 5 nav 화면+404. compose `web` 서비스.
- `src/stockpick/backtest/`: **M2 엔진 골격**(config·calendar·costs·strategy·ports·adapters·fakes·metrics·engine·benchmark·validation·demo). 룩어헤드(진입 t+1)·생존편향(UniversePort.constituents)·폐지청산(recovery_rate)·IS/OOS 워크포워드·purge·decay·등가중 벤치. ⚠️ 골격 유니버스=가격기반(FakeUniversePort)·cik 미해소 — 실데이터(종목마스터·ticker_history)는 S6 후.
- 명세: `docs/apis/{tiingo,eodhd}/`(tiingo 16섹션·eodhd 62섹션). 규칙: `.claude/rules/api-spec-reference.md`(data/** 편집 시 자동 로드).
- **검증됨**: 라이브 5종목(AAPL/NVDA/TSLA/MSFT/JNJ)×2124행, 분할 교차검증 통과(AAPL 4:1 adj 0.2425·NVDA 10:1 0.0998·TSLA 3:1 0.3333), 중복 0.

## 환경·검증·하네스 (compact-me 필독 — 안 그러면 재발견에 시간낭비)
- **검증(컨테이너 정본)**: `docker compose exec -T app sh -c 'ruff check src tests && ruff format --check src tests && mypy && pytest -q'`
- **의존성 추가(컨테이너 권한 함정)**: 그냥 `exec uv add` 안 됨 → CLAUDE.md Build 섹션의 우회 절차(uv.lock 바인드+`--no-sync`→`build`) 사용.
- **라이브 키**: `.env`(gitignore)에 `TIINGO_API_KEY`·`EODHD_API_KEY`(EODHD 결제 전·무료티어). compose가 interpolation 주입 — 키 변경 후 `docker compose up -d --no-deps app` 재생성.
- **하네스 BLOCKING**: ①`src/**` 변경 커밋엔 `docs/work-history/` 엔트리 필수(drift 차단) ②외부 API 코드는 `docs/apis/` 명세 참조(환각 금지) ③커밋 태그 강제(feat/fix/refactor/docs/test/chore/perf) ④푸시는 사용자 요청 시만 ⑤docs/plans→PLAN_STATUS·decisions/research→HOME·compose/pyproject→CLAUDE.md drift 동반.
- ⚠️ **커밋 메시지 함정**: 본문에 `(명령어)` 괄호 넣으면 verify-commit-msg 훅이 subject로 오파싱→차단. **메시지를 파일로 써서 `git commit -F <file>`** 로 커밋.
- ⚠️ **문서 페치**: 벤더 docs가 JS SPA면 `https://r.jina.ai/{url}` 렌더 프록시 경유(Tiingo 교훈).
- **work-history**: `docs/work-history/` + INDEX. **docs/learning/은 사용자 소유** — 건드리지 말 것.

## 🎯 남은 작업 (순서·실행단위 — "이거 하자" 하면 바로)

> ⚠️ 진행 순서 실측: 무료 1년치로 **M2 룰 슬라이스·M3 API/webapp·M2 백테스트 엔진 골격·#4·#2·#5 까지 코드층 완료**(데이터 신뢰성과 독립). **남은 핵심 = 결제 후 데이터 신뢰성(S6) + 백테스트 실검증** — 생존편향·룩어헤드는 실데이터(폐지 포함)라야 의미.

### 📋 후속 백로그 (M2 엔진+#4·#2·#5 후 — 영속 todo)

> 💰 = EODHD 결제 잠금해제(✅ **2026-06-18 결제 완료** — EOD Historical $19.99) → 이제 actionable / 🔮 = 무료 가능하나 가치는 데이터 후 / 🧹 = 코드 품질
> ⚠️ EODHD 플랜 능력(허용/미허용) = [[../apis/eodhd/pricing_plan/PLANS|PLANS.md]]. 우리 플랜은 가격(EOD·수정주가·폐지·분할배당·30년+) 전부 ✅, **재무(Fundamentals)는 ❌** → 재무는 SEC EDGAR(#재무-1 구현됨). 결제만으로 validated=true 아님 — 다년 수집+S6 게이트 필요.

- [ ] 💰→🟢 **TASK-E/S5**(결제됨·actionable·**4분해 a→b→c→d**): 다년 history + 전체 유니버스(폐지 포함) 적재 + 종목마스터(listed/delisted). 설계 `docs/superpowers/specs/2026-06-18-S5a-적재안전성-설계.md`
  - [x] ✅ **S5-a 적재 안전성**(2026-06-18): PG 코어 스키마(alembic 첫 실사용·stock+ticker_history+daily_bar·ADR-006)·G1 write read-merge-write(소실 봉인)·`data/db.py`(Parquet→PG 단방향 동기·cik""≡NULL). 237 passed. [[../work-history/2026-06-18-S5a-적재안전성]]
  - [x] ✅ **S5-b 종목마스터 채움**(2026-06-18): EODHD Common Stock 유니버스(`data/universe.py`)→PG stock 50,184 security(active 18,316+delisted 31,868)·listing_status·cik EDGAR enrich(16.4%)·ticker_history 스냅샷·G2 master_tickers. 다중클래스주 보존((cik,ticker) UNIQUE·migration 0003·GOOGL 버그수정)·demo 9/9. 246 passed. [[../work-history/2026-06-18-S5b-종목마스터]]
  - [x] ✅ **S5-c 벌크 가격 적재**(2026-06-18·파이프라인): `data/bulk.py`(run_bulk) — 종목마스터 대상 다년 EOD→Parquet(백테스트 진실원본)·체크포인트/재시도(G4)·verify 1회(G8 O(n²) 회피)·날짜 backfill(listed_at/delisted_at=가격 min/max·delisted만+source)·커버리지 요약(C1). Parquet 벌크만(PG daily_bar 동기 이연). 스모크 `--limit 20` PASS(259 passed). ⚠️ **전체 50,184 풀런=운영자 트리거**(`python -m stockpick.data.bulk`·수시간·재개). [[../work-history/2026-06-18-S5c-벌크가격]]
  - [ ] 🟢 **S5-d 실 UniversePort+S6**: 종목마스터 기반 UniversePort(G7)·**ticker_history EXCLUDE 구간중첩 제약(C2 — S5-b 무한스냅샷 대체 후)**·시점 cik 해소(TickerHistoryResolver·G9)·거래소 정밀화(EODHD OTC 폴백 보강)·S6 게이트→validated=true
- [ ] 💰 **실 UniversePort**: 종목마스터 기반 `UniversePort`(현 골격 `PriceDerivedUniverse` 가격기반 교체 — survivorship 정답)
- [ ] 💰 **S6 신뢰성 게이트** 통과 → 백테스트 수치 신뢰 → `meta.validated=true` 전환(§4.1)
- [ ] 🔮 **TickerHistoryResolver**: 시점별 ticker↔cik(SEC submissions 이력 — ticker 재사용 생존편향 정답). 현 `EdgarSnapshotResolver`는 현재 스냅샷만
- [x] ✅ **EDGAR 재무층 슬라이스(#재무-1, 2026-06-18)**: companyfacts 직접 JSON 파싱([ADR-005](../decisions/ADR-005-재무-직접파싱.md))·`FinancialFact`·PIT(filed<=as_of)·ROE/P/B 팩터→ranking factors 노출(결합 안함·§9-2). 라이브 9종목 4571 fact·7/9 ROE·5/9 P/B 실값. [[../work-history/2026-06-18-EDGAR-재무층]]
  - 후속 [ ] 🔮 **재무 커버리지 확장**: ① StockholdersEquity 변형 태그 폴백(JNJ=NCI 포함 태그라 연간 0) ② 다중클래스 주식수 합산(GOOGL/META dei shares=0 → P/B 불가) ③ TTM(4분기합) ROE ④ edgartools 광범위 정규화(~15필드) — ADR-005 재검토 트리거
- [ ] 🔮 **walk-forward·decay UI**: BacktestPage 에 IS/OOS·민감도(다년 데이터라야 통계 유의) / 파라미터 전체폼
- [ ] 🧹 **recharts 청크 코드스플릿**(>500KB) · 거래비용/벤치 비대칭 등 리뷰 Open Question(work-history 참조)

> 위 백로그 원천 = 각 work-history "후속" 섹션(2026-06-17 M2백테스트·#4·#2·#5). 이 목록이 단일 진입점.

### TASK-A: EODHD 명세 캐처 ✅ **완료**(커밋 397b244)
- `docs/apis/eodhd/` 62섹션 JSON + `_index.json` + README(HOME 링크). 워크플로우 `eodhd-spec-capture`(discover→capture). 189 엔드포인트, OK 54/PARTIAL 8.
- 인증 실측 = `?api_token=<KEY>` 쿼리, base `https://eodhd.com/api`, 심볼 `{TICKER}.{EX}`. 핵심 EOD = `GET /api/eod/{SYM}`(raw OHLC + `adjusted_close`→adj_factor).
- bulk-api-eod-splits-dividends 만 partial(보강 여지). 비핵심(intraday/options/crypto 등)도 전부 저장됨.

### TASK-B: 게이트 소실 미탐지 보강 ✅ **완료**(734a52f)
- `storage.py` `verify_parquet(expected=)` — 적재 전후 ticker 집합·행수 대조, missing/shortfall→VerificationError. `build_expected()`·`TickerExpectation`. pilot 누적 expected 전달. sabotage 검증 완료.
- ⚠️ S5 연결 시: expected 원천을 **종목마스터(상장+폐지 합집합)**로 교체해야 진짜 생존편향 가드(M1 §5 폐지 하한 결합, db-architect).

### TASK-C: adj_factor quantize ✅ **완료**(42df8d1)
- `src/stockpick/data/_adjust.py` 공유 `compute_adj_factor` — adjusted/raw 소수 12자리 quantize. storage scale 37→12. tiingo·eodhd 공용. (방향=adjusted/raw, 계약 adjusted=raw*adj_factor)

### TASK-D: EodhdSource 어댑터 ✅ **완료**(42df8d1)
- `src/stockpick/data/eodhd.py`: `EodhdSource(DataSource)`. `GET /api/eod/{TICKER}.{EX}`, 인증 `?api_token=`(쿼리), raw OHLC+`adjusted_close`→adj_factor(공유헬퍼), value=None. `iter_universe` 폐지 포함(exchange-symbol-list 활성+delisted=1 병합). cik="" (EODHD 미제공). 모킹 26테스트.

### TASK-E: S5 전체 유니버스 + S6 게이트 (EODHD 결제 $19.99 후 라이브)
- 전체 미국 종목(폐지 포함) 벌크 적재 → 생존편향-correct. + 재무 EDGAR 결합(merge_asof PIT). S6 신뢰성 게이트 전항목 PASS → **M1 완료 선언** → M2 백테스트.
- ⛔ **라이브 전 BLOCKING(키 누출)**: EODHD 토큰이 URL 쿼리(`?api_token=`)라 **httpx 자체 INFO 로거가 완성 url(토큰 포함)을 로깅**. 우리 코드는 비노출이나 httpx 라이브러리 로거는 못 끔 → **진입점/로깅설정에서 `logging.getLogger("httpx").setLevel(WARNING)` 필수**(EODHD 라이브 실행 전).
- 선결: ①EODHD expected 원천=종목마스터(TASK-B 후속) ②EDGAR 재무층 구현(edgartools, `financial` fiscal_period≠disclosed_at) + **cik 매핑**(EODHD가 CIK 미제공 → EDGAR ticker→CIK 보강, 조인 기준) ③alembic 마이그레이션(stock cik PK·ticker_history·daily_bar — db-architect) ④**write read-merge-write 전환**(현 `(ticker,year)` 통파일 덮어쓰기는 같은연도 증분 부분호출 시 소실 — 일일증분 전 필수, docstring 경고만 박힘) ⑤EODHD 라이브 진입점은 `configure_logging()` 호출 확인(httpx 토큰가드 — 코드화됨, pilot.main 적용).
- ✅ 리뷰 반영(커밋 7f3b286): 양수성 게이트(음수/0 가격·adjusted 차단) · httpx 가드 코드화 · _adjust 단위테스트 · nits. 미반영(선택): iter_universe 부분실패·교차거래소 중복 테스트.

## 미해결·주의
- EDGAR 재무층 미구현(M2 직전) — edgartools ~15필드 정규화 정확도 표본검증 필요.
- EODHD 폐지 가격 깊이·배당 정확도 = 가입 후 표본 실측.
- alembic 마이그레이션·`ticker_history` 테이블 미구현(db-architect, S5 선결).
- 6개월 주기 데이터소스 약관·가격 재검증.

## 핵심 파일 인덱스
- 결정: `docs/decisions/ADR-001~003`. 기획: `docs/plans/stock-1st_plan.md`(기준선)·`M1-데이터파이프라인.md`(스펙)·`PLAN_STATUS.md`(현황).
- 리서치: `docs/research/2026-06-16-미국주식-데이터소스.md`·`2026-06-17-webapp-stack-버전.md`. 명세: `docs/apis/{tiingo,eodhd}/`.
- 코드: `src/stockpick/{types.py, data/{source,tiingo,eodhd,_adjust,ingest,storage,pilot}.py, rules/{factors,ranking,_scan}.py, api/{app,deps,models,routes/*}.py, backtest/{config,calendar,costs,strategy,ports,adapters,fakes,metrics,engine,benchmark,validation,demo}.py}` + `webapp/src/`. 계약 규칙: `.claude/rules/{python-conventions,api-spec-reference,logging-rules,webapp-conventions}.md`.
- 커밋 흐름: 7d60ab9(M0)→606ba0b(M1 S0-S1)→8e5d136(미장아키)→24b030b(Docker)→2f4d496(계약)→e57b8d6·982574d(Tiingo명세)→61b55c0(어댑터)→0f69a53(저장·파일럿)→096e7f3(키주입)→11fedce(EODHD확정).
