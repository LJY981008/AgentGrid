# Sub-project B — momentum × ROE 하드필터 결합 룰 (설계 스펙)

> 6 전문가 다관점 비평(퀀트방법론·백테스트정확성·구현타당성·과적합적대·룰설계) 판정 = **수정 후 GO**. 골격 5/5 건전, BLOCKING 다수 반영. 브레인스토밍 승인(2026-07-01).

## 1. 배경 · 목표

공식 신뢰성 게이트(2000~2026·10fold) 완주 → **momentum 단일팩터 = 깨끗한 측정에서 진짜 무알파**(validated=false·R-2 PASS·전폴드 음수 excess). Sub-project A 완료로 임의 시점·종목 ROE 를 **PIT(filed≤t)·생존편향-안전**하게 획득(2.68M fact·12,607 cik·verify passed). 정지점3 probe: 전체 유니버스 ROE 산출율 21.76%(2013+ ~24%).

**목표(B v1)**: momentum 에 **품질(ROE>0 흑자) 하드필터**를 결합한 룰이 momentum 단일팩터보다 나은지 **validated 게이트로 정직 검증**. plan §4.1 "깨끗한 fail 후 다팩터 피벗" 의 첫걸음.

## 2. 사전결정 (재논쟁 금지 — ADR-010 · roadmap)

- **방식 C 하드필터**(가중 0·이진 게이트). z-score/rank-sum blend 금지(microcap 분모붕괴 폭발·ADR-010 2차폭발 동형).
- 결측 재무 = **명시 배제**(중립채움 금지 = 은닉 생존편향).
- **pre-registration**: 임계·config 게이트 전 동결(`compute_rule_signature`)·튜닝으로 pass 금지.
- momentum canonical(ADR-010 동결): lookback 252/skip 21/top-decile(pct 0.1·floor 20)/기간 2000~2026/유동성 close≥$5·ADV20≥$1M/동일비용 벤치.

## 3. 룰 (리밸 t · PIT · **ROE→momentum 순서**)

전문가 권장 순서 채택(생존자 붕괴 완화·벤치 대칭·MNAR 노출 동시 개선):

1. **유동성 유니버스**(≤t·close≥$5·ADV20≥$1M).
2. **cik 해소**(`PitIdentityResolver`·on=t·다중매칭=배제+카운트, **raise 아님**).
3. **ROE 산출**(`financial_factors`·`latest_as_of`·**filed≤t**·**동일 FY**·**recency≤max_age**).
4. **품질 필터: ROE 산출가능 ∧ ROE>0(흑자)** → 흑자 유동 유니버스로 축소.
5. **momentum top-decile**(canonical)을 4의 축소 유니버스에 적용.
6. **생존자 등가중**.

- 룩어헤드: 재무 `disclosed_at(filed)≤t`. 생존편향: 폐지 포함(MasterUniverse `delisted_at+1`). ROE>0 = 실제로는 **흑자 ∧ 양(+)equity solvency 결합필터**(자본잠식 우량주 역선택 배제 — 명문화·배제수 로그).

## 4. config + rule_signature (BLOCKING · H1 — 최우선)

- `factor_filter = {enabled: bool, factors: tuple[str], roe_min: Decimal, max_age_days: int}` — configurable(ROE-only↔+PB). **기본 off**.
- `compute_rule_signature`(s6_gate.py) 에 `factor_filter_enabled`·`factor_filter_factors(정렬)`·`roe_min`·`max_age_days` 추가. **off = 기존 momentum canonical signature bit-identical**(하위호환).
- 같은 커밋 **3자 동시갱신**: `canonical_gate_config` · `ranking_rule_signature` · `api/routes/ranking`(서빙 flip 다리). RESUME B1 함정(3자 미동시=영원한 false) 회피.
- 두 임계(coverage/survivors) + max_age + roe_min = **s6_gate 모듈 상수 동결**(`_ROE_MIN`·`_MAX_AGE_DAYS`·`_ROE_COVERAGE_OBS`·`_MIN_SURVIVORS`), config 미노출.

## 5. 벤치마크 대칭 + 귀인 감사 (BLOCKING · H3 · H2)

- **벤치 대칭(H3)**: `equal_weight_universe` 벤치에 **동일 ROE>0 필터 훅**(engine 과 필터코드 공유). 벤치 = "흑자 유동 유니버스 등가중"(momentum 만 뺀). 비대칭(룰=흑자∩decile vs 벤치=유동전체) 제거. ROE-first 순서라 자연.
- **귀인 감사(H2)**: **순수 ROE 벤치**(유동∩ROE>0 등가중·momentum 없음)를 **감사지표로 병기**(게이트 임계 아님·rule_signature 무영향). 판정 리포트에 "excess 가 momentum 인크리먼트인지 ROE 프리미엄(QMJ/Novy-Marx) 베이스라인인지" 노출 → "momentum 살아났다" 오귀인 차단.

## 6. 게이트 (검증 판정)

- **validated 판정 = 기존 G-1~G-8 · R-2(S6-b)로만**.
- **G-5c(재무커버리지) = 관측지표 강등(H9)** — pass/fail 아님. 이유: probe docstring 이 목적을 "G-5c 임계 입력"이라 자인 + 21.76% 실측 본 뒤 "과반(50%)" = R1 방화벽 '진단분포로 임계 고르기' 금지 위반. 50% 초과가 무편향 미보장(MNAR).
  - `s6_gate_result.json` 에 fold별 기록: top-decile ROE 커버율 · 필터 생존종목수 · MNAR skew(커버/미커버 momentum·후속수익 차이). **caveat 로 판정문 상시 첨부**.
  - 생존종목수: 리밸별 <floor(canonical 20) = "측정불가" 마킹 → fold 내 측정불가 비율 > 사전동결 임계면 **fold 제외**(fail 아님). 값=canonical floor 재사용(자의적 '절반' 제거).
- **필터 후 폐지비율로 G-5 재검증**(흑자필터가 저폐지 선택 → 생존편향 재유입 점검).

## 7. 다중검정 방지 메커니즘 (BLOCKING · H10)

- 규율뿐 아니라 **메커니즘**: 게이트 시도 이력(signature+timestamp) **append-only 로그** 영속(`unlink` 대신 timestamped 아카이브). `s6_gate_result.json` 에 `pre_registered_signature` 를 게이트 실행 **전** 커밋. 탐색 config ≠ 게이트 config(코드경로 분리·탐색=validated flip 불가 플래그).

## 8. 착수 전 게이트-소진 밖 dry-run probe 3종 (H4 · 지금 실행)

게이트 1회 소진에 불포함·백테스트 미실행·**결과로 임계 낮추기 금지(R1)**:
- (a) 리밸별 top-decile 내 ROE 커버율 · 생존종목수 분포.
- (b) `PitIdentityResolver` 다중매칭 raise 실측(2000~2026 전 리밸).
- (c) 커버/미커버 종목 momentum 분포 · 후속수익 차이(MNAR 심각도).

다수 fold 측정불가면 → "현 커버리지에서 측정 불가"라는 **정직한 no-go**(validated=false).

## 9. 구현 요구 (전문가 BLOCKING)

- **H5 STALE 상한**: `latest_as_of` 에 `max_age_days`(사전동결 ~18개월=연간주기+공시시차). 초과 = ROE 산출불가. TDD: 24개월 전 stale 흑자 → 탈락.
- **H8 동일 FY**: ROE 분자(NetIncomeLoss)·분모(StockholdersEquity)를 **같은 FY** 강제(현재 독립 `latest_as_of` → 다른 FY 조합 가능). period 불일치 = 배제. TDD.
- **H6 성능**: `latest_as_of` 가 매번 2.68M 전스캔 → decile×concept×리밸×fold OOM 위험. `dict[(cik,concept)]→disclosed_at 정렬` 1회 전처리 + **bisect**, 또는 duckdb_cache `financial_fact` as_of 푸시다운. **1 fold walltime·peak RSS 실측 벤치 후 12g 내 확인**(추측 금지).
- **H7 `_rank_at` 재배선**: ROE-first 순서로 tradable→cik 조기해소→ROE 필터→momentum decile→등가중. decile 분모 = 필터 생존자 수.
- **다중매칭**: `cik_for` 다중매칭 = 리밸서 해당 종목만 배제+카운트(fold 계속). ticker_history 중첩 무결성은 **게이트 진입 전 pre-flight(G-7 계열)** 로 fail-fast.
- **G-5c 배선**: 관측지표를 `S6GateResult` per-fold 필드·`write_s6_gate_result` 에 동시 배선(조용한 통과 방지).

## 10. 검증 (TDD)

- 필터: ROE>0 흑자 보존 · 적자/무ROE/자본잠식(equity≤0) 탈락 · **룩어헤드 sabotage**(미래 filed 배제) · **stale sabotage**(24개월 초과 배제) · **동일 FY sabotage**(불일치 배제) · 생존편향(폐지 흑자 보존).
- signature: on≠off · **off=momentum canonical bit-identical**(하위호환 회귀).
- 벤치 대칭: 벤치에 필터 적용 · 순수 ROE 벤치 산출.
- 다중매칭 격리 배제 회귀.
- 통합: engine+필터 산출 · rule_signature 봉인.

## 11. caveat (정직 판정 상시 첨부)

ROE>0=흑자∧solvency 결합필터(음-equity 우량주 배제·fold별 로그) / MNAR 잔존·커버=측정 신뢰성 하한일 뿐 무편향 아님 / ROE stale up-to-15mo(FY-only) / 이 룰=순수 momentum 아닌 "momentum ∩ 공시가능 ∩ 흑자" 합성.

## 12. 범위

- **이번(B v1)**: 위 룰 + config/signature + 벤치 대칭 + 귀인 감사 + G-5c 관측 + dry-run 3종 + 게이트 1 config(ROE-only 동결) 실행 → validated 판정.
- **v2 로드맵**: raw ROE → operating/gross profitability(분모=총자산·Novy-Marx·QMJ 부호왜곡 제거) / TTM(4분기 합) / +PB(v1 dead config 금지·별도 ADR·pre-register).
- **범위 밖**: 가중 튜닝 · rank-sum blend · 재무로 유니버스 멤버십 결정.

## 13. 의존 · 재사용

`rules.factors.financial_factors`(FY강제·성능 확장) · `rules._financials.latest_as_of`(max_age 추가) · `backtest.identity.PitIdentityResolver`(다중매칭 배제) · `backtest.adapters.MasterUniverse` · `backtest.s6_gate`(signature·G-5c·pre-flight) · `backtest.benchmark`(대칭 필터) · `backtest.engine._rank_at`(재배선) · `backtest.coverage_probe`(dry-run 재사용).
