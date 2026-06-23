# ADR-009 — S6-b 신뢰성 게이트: momentum 룰 검증 기준 사전 동결

- 상태: 채택 (2026-06-23)
- 맥락: [[2026-06-23-S6b-신뢰성게이트]] · 후속 of [[ADR-004-백테스트-프레임워크-자체구현]]·[[ADR-007-백테스트-DuckDB-persistent-캐시]]
- 기획: stock-1st_plan §4.1(BLOCKING)·§4.4(검증)·M1 §6(신뢰성 게이트)

## 맥락

`meta.validated=false` 가 ranking/backtest API 에 하드코딩돼 있다(룰 미입증 — 백테스트 엔진은 구현됐으나 다년 검증 미통과). 이를 `true` 로 뒤집으려면 현재 momentum 룰(프로토타입·단일팩터)이 전구간(1962~2026·50,184종목·폐지 포함) 백테스트에서 **out-of-sample 강건**함을 입증해야 한다.

⚠️ 위험: 게이트를 "통과시키기" 도구로 만들면(임계를 데이터로 고르면) **과적합**(M1 §6 위반). 게이트는 **정직한 판정 도구**여야 한다. momentum 은 이미 등가중 언더퍼폼·생존편향 붕괴 정황이 있어 **fail 가능성이 높고, false 유지가 정답일 수 있다**.

## 결정

**판정 기준을 사전 동결(pre-registration)** 한다 — 데이터를 보기 전에 임계를 못 박고, 코드에 **모듈 상수**로 박아 config 노브로 못 흔든다. 전 기준 AND. 하나라도 fail → `validated=false` 유지.

| # | 기준 | 임계(동결) | 근거 |
|---|---|---|---|
| G-1 | IS 자체 성과 | 전 fold `is_failed=False`(IS sharpe>0) | IS조차 음수면 룰 실패(검증 의미 없음) |
| G-2 | OOS 방어율 | 전 fold `decay_ratio ≥ 0.5`(`_DECAY_MIN`) | WF효율 >50% 수용·<30%=과적합(퀀트 관례)·전 fold=시간 안정성 |
| G-3 | OOS 절대성과 | **전 fold** OOS 등가중 벤치 대비 초과 > 0 | 무비용 등가중(이론상한) 못 이기면 종목선택 무가치. ⚠️ 집계=전 fold(G-1·G-2 와 동일 보수성) — 평균은 한 fold 폭등이 음수 fold 를 가려 통과시킴(Task2 리뷰 반영·임계 ">0" 동결·집계만 정직 refinement·데이터 보기 전) |
| G-4 | 분할 수 | n_folds ≥ 10(`_N_FOLDS`) | ~64년→fold당 ~6.5년·OOS 우연 1회 배제 |
| G-5 | 폐지 커버리지 | delisted 비율 ≥ 30%(`_DELISTED_MIN`) AND `n_delisted_liquidations > 0` | 생존편향 가드 死문자 방지(실측 31,868=63.5%) |
| G-6 | 비용 민감도 | cost_bps 5/10/15bps **세 시나리오 모두 G-2** | gap에 임계 안 둠(과적합 금지)·비용 종속이면 fragile |
| G-7 | 무결성 verify | `bulk --verify` PASS(`VerificationReport.passed`) | S6 진입 선결 |
| G-8 | 재현성 | config fingerprint 동일·bit-identical | DuckDB momentum 봉인(ADR-007 회귀) |

## 대안 (기각)

- **데이터로 임계 고르기**(예: "decay 0.5 못 넘으면 0.4로 완화") — **기각**: 과적합·정직성 위반(M1 §6). 사전 동결의 핵심.
- **CPCV(Combinatorial Purged CV)·다중 임계 최적화** — **기각**: 단일 프로토타입 룰 판정엔 과설계. anchored walk-forward + purge(기존 `validation.walk_forward`)로 충분. 향후 다팩터 룰에서 재고.
- **벤치마크 = 시장지수(S&P500)** — **기각**: 무비용 등가중 유니버스가 더 보수적 상한(지수는 대형주 편중·우리 유니버스와 구성 불일치). `equal_weight_universe` 재사용.
- **게이트 통과를 목표로 룰 튜닝** — **기각**: 게이트는 판정 도구지 룰 개발 도구 아님. fail→false 유지가 정직한 결과.

## 민감도 범위

- **비용(±cost_bps) = 즉시**(G-6·`sensitivity_analysis`). 거래비용 가정에 룰이 종속이면 fragile.
- **데이터 완전성(1%/0.5% 결측 임계) = 후속**(M1 원의도). per-ticker completeness 메타가 선결이라 이번 범위 밖.

## 결과

(Task4 풀 실행 후 기입 — 각 G 결과·종합 판정·validated 결정. ⚠️ zero-adjusted(adj_factor=0)로 G-7 verify fail 시 데이터 품질 블로커로 정직히 노출.)
