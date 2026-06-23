"""S6-b 신뢰성 게이트 — momentum 룰 다년 백테스트 검증 → validated 판정.

게이트는 "통과시키기"가 아니라 **정직한 판정 도구**(ADR-009). 판정 기준(G-1~G-8)은 데이터를
보기 전에 동결한 **모듈 상수**(`_DECAY_MIN`·`_N_FOLDS`·`_DELISTED_MIN`) — config 노브로 못
흔든다(데이터로 임계 고르기 = 과적합 금지·M1 §6). 전 기준 AND, 하나라도 fail → validated=false 유지.

모듈 경계(python-conventions): backtest 층 — data/rules/backtest 만 의존(api/prometheus 금지).
결과불변(BLOCKING): 게이트는 백테스트 수치를 바꾸지 않는다. 비용 민감도는 `replace(config, ...)`
로 신규 config 를 만들 뿐, 원 config·ports 를 변형하지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from .benchmark import equal_weight_universe
from .engine import run
from .validation import walk_forward

if TYPE_CHECKING:
    from decimal import Decimal

    from .config import BacktestConfig
    from .ports import IdentityResolver, PriceSeriesPort, UniversePort
    from .strategy import Strategy
    from .validation import Fold

logger = logging.getLogger(__name__)

# 사전 동결 임계(ADR-009·G-1~G-8) — 모듈 상수. config 노브 아님(데이터로 임계 고르기=과적합 금지).
_DECAY_MIN = 0.5  # G-2·G-6 OOS 방어율(decay=OOS/IS sharpe) 하한
_N_FOLDS = 10  # G-4 최소 워크포워드 분할 수
_DELISTED_MIN = 0.30  # G-5 유니버스 폐지 커버리지 하한(실측 63.5%)


def _default_cost_variants() -> tuple[Decimal, ...]:
    """사전 동결 비용 시나리오(G-6) — 5/10/15bps(Decimal). 회전분 bps, 10bps 중심 ±5.

    함수로 지연 생성(모듈 로드시 Decimal import 회피). 호출부 임의 변경은 사전동결 위반.
    """
    from decimal import Decimal as D

    return (D("5"), D("10"), D("15"))


def _cost_key(cost_bps: Decimal) -> str:
    """비용 → 안정적 dict 키(`5bps`·`10bps`·`15bps`). normalize 로 의미동일=키동일."""
    return f"{cost_bps.normalize():f}bps"


def _worst_decay(folds: list[Fold]) -> float:
    """fold 들의 최악(min) decay_ratio. None(IS<=0 기각 또는 신호미약)·빈 fold = 0.0(G-2 미달 표식).

    G-2 는 '전 fold decay≥0.5'라 binding 통계는 최악값. None 은 비율 무의미(방어 불가)이므로
    0.0 으로 환산해 보수적으로 미달 처리(조용한 통과 금지). ⚠️ None 두 경우(IS<=0 기각·0<IS<ε
    신호미약)를 0.0 으로 **의도적 병합** — 민감도 메트릭엔 둘 다 ≥0.5 미달이라 무방. 기각/신호미약
    구분이 필요한 호출부(Task2 G-1)는 이 float 가 아니라 `Fold.guard.is_failed` 를 직접 본다.
    """
    if not folds:
        return 0.0
    return min((f.guard.decay_ratio if f.guard.decay_ratio is not None else 0.0) for f in folds)


def walk_forward_by_cost(
    config: BacktestConfig,
    *,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    strategy: Strategy,
    cost_bps_variants: tuple[Decimal, ...] | None = None,
    n_folds: int = 3,
    purge_gap_days: int | None = None,
) -> dict[Decimal, list[Fold]]:
    """비용 변동별 워크포워드 fold — {cost_bps: folds}. 결과불변: replace 로 신규 config 만 사용.

    run_s6_gate(Task2) 가 baseline 비용 fold 를 재사용(G-1/G-2/G-3)하고 전 비용을 G-6 에 쓰므로
    fold 를 그대로 반환(decay 만 반환하면 재계산 낭비). 비용은 회전분에만 작용(turnover×bps)이라
    각 비용이 독립 백테스트.
    """
    variants = cost_bps_variants if cost_bps_variants is not None else _default_cost_variants()
    logger.info("비용 민감도 워크포워드 시작: variants=%s, n_folds=%d", variants, n_folds)
    by_cost = {
        c: walk_forward(
            replace(config, cost_bps=c),
            price_port=price_port,
            universe_port=universe_port,
            identity=identity,
            strategy=strategy,
            n_folds=n_folds,
            purge_gap_days=purge_gap_days,
        )
        for c in variants
    }
    logger.info(
        "비용 민감도 워크포워드 완료: %d 비용 변동, fold수=%s",
        len(by_cost),
        {str(c): len(f) for c, f in by_cost.items()},
    )
    return by_cost


def sensitivity_analysis(
    config: BacktestConfig,
    *,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    strategy: Strategy,
    cost_bps_variants: tuple[Decimal, ...] | None = None,
    n_folds: int = 3,
    purge_gap_days: int | None = None,
) -> dict[str, float]:
    """비용 민감도(G-6) — 각 비용서 최악 decay_ratio 매핑(`GuardReport.sensitivity` 채움).

    값=해당 비용 fold 최악 decay(None/빈 fold=0.0). 비용 종속이면(어떤 비용서 0.5 미달)
    fragile = G-6 fail. 결과불변: 원 config·ports 미변형(replace 신규 객체).
    """
    by_cost = walk_forward_by_cost(
        config,
        price_port=price_port,
        universe_port=universe_port,
        identity=identity,
        strategy=strategy,
        cost_bps_variants=cost_bps_variants,
        n_folds=n_folds,
        purge_gap_days=purge_gap_days,
    )
    if all(not folds for folds in by_cost.values()):
        # 전 비용 fold 0건 = 데이터 부족(분할 불가)이지 "측정된 비용 취약"이 아님 — 정직히 구분.
        # 값은 fail-closed(0.0) 유지하나 사유를 로그로 노출(G-4 분할수가 진짜 차단 기준).
        logger.warning("비용 민감도: 전 비용 fold 0건 — 데이터 부족(측정 실패 아님·G-4 미달 사유)")
    return {_cost_key(c): _worst_decay(folds) for c, folds in by_cost.items()}


def _baseline_cost() -> Decimal:
    """게이트 baseline 운영 비용(10bps) — G-1/G-2/G-3 평가·rule_signature 기준. 변동 중앙값."""
    from decimal import Decimal as D

    return D("10")


@dataclass(frozen=True, slots=True)
class S6GateResult:
    """S6-b 게이트 판정 — 전 기준(G-1~G-8) AND. 하나라도 fail → validated=false 유지(정직 판정)."""

    passed: bool
    rule_signature: str  # baseline config.fingerprint() — flip(Task3) signature 일치 기준
    n_folds: int
    g1_is_pass: bool  # 전 fold IS sharpe>0(is_failed=False)
    g2_decay_pass: bool  # 전 fold decay_ratio>=_DECAY_MIN
    g3_excess_pass: bool  # OOS 등가중 벤치 평균 초과>0
    g4_nfolds_pass: bool  # n_folds>=_N_FOLDS
    g5_delisted_pass: bool  # 폐지비율>=_DELISTED_MIN AND 누적 폐지청산>0
    g6_cost_pass: bool  # 전 비용(5/10/15bps) 최악 decay>=_DECAY_MIN
    g7_verify_pass: bool  # bulk --verify PASS(외부 측정)
    g8_reproducible: bool  # baseline fold 재실행 bit-identical
    fold_decays: tuple[float | None, ...]
    sensitivity: dict[str, float]
    delisted_ratio: float
    n_delisted_liquidations: int
    oos_excesses: tuple[float, ...]  # per-fold OOS 등가중 초과(감사·G-3 = 전 fold>0)
    notes: tuple[str, ...] = ()


def _failure_notes(
    *,
    g1: bool,
    g2: bool,
    g3: bool,
    g4: bool,
    g5: bool,
    g6: bool,
    g7: bool,
    g8: bool,
) -> tuple[str, ...]:
    """실패 기준을 정직히 나열(통과면 빈 tuple) — 판정 리포트·validated=false 사유 추적."""
    labels = {
        "G-1": g1,
        "G-2": g2,
        "G-3": g3,
        "G-4": g4,
        "G-5": g5,
        "G-6": g6,
        "G-7": g7,
        "G-8": g8,
    }
    failed = [k for k, ok in labels.items() if not ok]
    if not failed:
        return ()
    return (f"미통과 기준: {', '.join(failed)} (전부 AND — 하나라도 fail 시 validated=false 유지)",)


def evaluate_criteria(
    *,
    rule_signature: str,
    fold_decays: tuple[float | None, ...],
    fold_is_failed: tuple[bool, ...],
    n_folds: int,
    oos_excesses: tuple[float, ...],
    delisted_ratio: float,
    n_delisted_liquidations: int,
    sensitivity: dict[str, float],
    verify_passed: bool,
    reproducible: bool,
) -> S6GateResult:
    """사전 동결 임계(G-1~G-8)를 측정값에 적용 → S6GateResult. **순수 함수**(백테스트 비실행).

    측정·실행은 run_s6_gate 가, 임계 비교·AND 판정은 여기서 — 임계 동결 단위테스트를 위해 분리.
    빈 fold(데이터 부족)는 G-1/G-2/G-3 가 `bool(...)` 으로 False(조용한 통과 금지·G-4 가 진짜 차단).
    """
    g1 = bool(fold_is_failed) and not any(fold_is_failed)
    g2 = bool(fold_decays) and all(d is not None and d >= _DECAY_MIN for d in fold_decays)
    # G-3 = 전 fold 초과>0(G-1·G-2 와 동일 "전 fold" 보수성) — 평균은 한 fold 폭등이 음수 fold 를
    # 가려 등가중 못 이기는 룰을 통과시킴(ADR-009 의도 위반). 임계는 ">0" 동결, 집계만 전 fold.
    g3 = bool(oos_excesses) and all(e > 0.0 for e in oos_excesses)
    g4 = n_folds >= _N_FOLDS
    g5 = delisted_ratio >= _DELISTED_MIN and n_delisted_liquidations > 0
    g6 = bool(sensitivity) and all(v >= _DECAY_MIN for v in sensitivity.values())
    g7 = verify_passed
    g8 = reproducible
    passed = all((g1, g2, g3, g4, g5, g6, g7, g8))
    return S6GateResult(
        passed=passed,
        rule_signature=rule_signature,
        n_folds=n_folds,
        g1_is_pass=g1,
        g2_decay_pass=g2,
        g3_excess_pass=g3,
        g4_nfolds_pass=g4,
        g5_delisted_pass=g5,
        g6_cost_pass=g6,
        g7_verify_pass=g7,
        g8_reproducible=g8,
        fold_decays=fold_decays,
        sensitivity=dict(sensitivity),
        delisted_ratio=delisted_ratio,
        n_delisted_liquidations=n_delisted_liquidations,
        oos_excesses=oos_excesses,
        notes=_failure_notes(g1=g1, g2=g2, g3=g3, g4=g4, g5=g5, g6=g6, g7=g7, g8=g8),
    )


def _reproducible(
    baseline_folds: list[Fold],
    config: BacktestConfig,
    *,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    strategy: Strategy,
) -> bool:
    """G-8 — baseline fold 중 OOS 최단 구간 재실행해 bit-identical 확인(결정성). fold 없으면 False.

    재현성 강한 봉인(DuckDB↔메모리 bit-identical)은 Task5 회귀 테스트가 담당. 여기선 동일 입력
    재실행이 동일 결과인지(숨은 비결정성 차단)만 저비용 확인 — 가장 짧은 OOS 1건만.
    ⚠️ BacktestResult 전체(phase_profile 포함) eq 라 **profile=None 전제**(게이트는 profile 미주입).
    """
    if not baseline_folds:
        return False
    f = min(baseline_folds, key=lambda fl: (fl.oos_end - fl.oos_start).days)
    oos_cfg = replace(config, cost_bps=_baseline_cost(), start=f.oos_start, end=f.oos_end)
    rerun = run(
        oos_cfg,
        price_port=price_port,
        universe_port=universe_port,
        identity=identity,
        strategy=strategy,
    )
    return rerun == f.oos_result


def run_s6_gate(
    config: BacktestConfig,
    *,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    strategy: Strategy,
    delisted_ratio: float,
    verify_passed: bool,
    n_folds: int = _N_FOLDS,
    purge_gap_days: int | None = None,
    cost_bps_variants: tuple[Decimal, ...] | None = None,
) -> S6GateResult:
    """전구간 워크포워드 + 비용 민감도 + 벤치초과 + 폐지커버리지 → G-1~G-8 판정(S6GateResult).

    측정: walk_forward_by_cost 1회로 baseline(10bps) fold 재사용(G-1/G-2/G-3) + 전 비용(G-6).
    `delisted_ratio`(G-5a)·`verify_passed`(G-7)는 외부 측정(CLI 가 스냅샷·verify_parquet 산출) 주입
    — 게이트는 조용히 추측 안 함. 결과불변: replace 신규 config 만 사용(원 config·ports 불변).
    """
    if not (0.0 <= delisted_ratio <= 1.0):
        # 외부 측정 경계 검증 — 비물리 값이 G-5 판정을 조용히 왜곡 금지(loud fail).
        msg = f"delisted_ratio 는 [0,1] 비율(받음={delisted_ratio})"
        raise ValueError(msg)
    baseline = _baseline_cost()
    variants = cost_bps_variants if cost_bps_variants is not None else _default_cost_variants()
    if baseline not in variants:
        # baseline fold 재사용 불가 = 조용한 추측 금지(loud fail).
        msg = f"baseline 비용 {baseline} 가 변동 {variants} 에 없음 — G-1/G-2/G-3 평가 불가"
        raise ValueError(msg)

    by_cost = walk_forward_by_cost(
        config,
        price_port=price_port,
        universe_port=universe_port,
        identity=identity,
        strategy=strategy,
        cost_bps_variants=variants,
        n_folds=n_folds,
        purge_gap_days=purge_gap_days,
    )
    baseline_folds = by_cost[baseline]
    fold_decays = tuple(f.guard.decay_ratio for f in baseline_folds)
    fold_is_failed = tuple(f.guard.is_failed for f in baseline_folds)

    # G-3: 각 OOS fold 의 룰 수익 vs 등가중 전체 유니버스(무비용 이론상한) 초과 — 평균>0.
    excesses: list[float] = []
    for f in baseline_folds:
        bench = equal_weight_universe(
            replace(config, cost_bps=baseline, start=f.oos_start, end=f.oos_end),
            price_port=price_port,
            universe_port=universe_port,
        )
        excesses.append(float(f.oos_result.total_return - bench.total_return))

    # G-5b: 누적 폐지청산(생존편향 가드 발동 증거).
    cum_delisted = sum(f.oos_result.n_delisted_liquidations for f in baseline_folds)
    # G-6: 비용 민감도.
    sensitivity = {_cost_key(c): _worst_decay(folds) for c, folds in by_cost.items()}
    # G-8: 결정성 재실행.
    reproducible = _reproducible(
        baseline_folds,
        config,
        price_port=price_port,
        universe_port=universe_port,
        identity=identity,
        strategy=strategy,
    )
    rule_signature = replace(config, cost_bps=baseline).fingerprint()

    result = evaluate_criteria(
        rule_signature=rule_signature,
        fold_decays=fold_decays,
        fold_is_failed=fold_is_failed,
        n_folds=len(baseline_folds),
        oos_excesses=tuple(excesses),
        delisted_ratio=delisted_ratio,
        n_delisted_liquidations=cum_delisted,
        sensitivity=sensitivity,
        verify_passed=verify_passed,
        reproducible=reproducible,
    )
    worst_excess = min(result.oos_excesses) if result.oos_excesses else None
    logger.info(
        "S6-b 게이트 판정: passed=%s, n_folds=%d, worst_oos_excess=%s, sensitivity=%s, notes=%s",
        result.passed,
        result.n_folds,
        worst_excess,
        result.sensitivity,
        result.notes,
    )
    return result
