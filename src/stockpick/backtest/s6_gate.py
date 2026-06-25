"""S6-b 신뢰성 게이트 — momentum 룰 다년 백테스트 검증 → validated 판정.

게이트는 "통과시키기"가 아니라 **정직한 판정 도구**(ADR-009). 판정 기준(G-1~G-8)은 데이터를
보기 전에 동결한 **모듈 상수**(`_DECAY_MIN`·`_N_FOLDS`·`_DELISTED_MIN`) — config 노브로 못
흔든다(데이터로 임계 고르기 = 과적합 금지·M1 §6). 전 기준 AND, 하나라도 fail → validated=false 유지.

모듈 경계(python-conventions): backtest 층 — data/rules/backtest 만 의존(api/prometheus 금지).
결과불변(BLOCKING): 게이트는 백테스트 수치를 바꾸지 않는다. 비용 민감도는 `replace(config, ...)`
로 신규 config 를 만들 뿐, 원 config·ports 를 변형하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from .benchmark import equal_weight_universe
from .config import _DEFAULT_RETURN_CAP
from .engine import run
from .validation import walk_forward

if TYPE_CHECKING:
    from datetime import date
    from decimal import Decimal

    from .config import BacktestConfig
    from .ports import IdentityResolver, LiquidityPort, PriceSeriesPort, UniversePort
    from .strategy import Strategy
    from .validation import Fold

logger = logging.getLogger(__name__)

# 사전 동결 임계(ADR-009·G-1~G-8) — 모듈 상수. config 노브 아님(데이터로 임계 고르기=과적합 금지).
_DECAY_MIN = 0.5  # G-2·G-6 OOS 방어율(decay=OOS/IS sharpe) 하한
_N_FOLDS = 10  # G-4 최소 워크포워드 분할 수
_DELISTED_MIN = 0.30  # G-5 유니버스 폐지 커버리지 하한(실측 63.5%)

_RESULT_NAME = "s6_gate_result.json"  # 게이트 판정 영속(flip 단일 진실원천)


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
    liquidity_port: LiquidityPort,
    cost_bps_variants: tuple[Decimal, ...] | None = None,
    n_folds: int = 3,
    purge_gap_days: int | None = None,
) -> dict[Decimal, list[Fold]]:
    """비용 변동별 워크포워드 fold — {cost_bps: folds}. 결과불변: replace 로 신규 config 만 사용.

    run_s6_gate(Task2) 가 baseline 비용 fold 를 재사용(G-1/G-2/G-3)하고 전 비용을 G-6 에 쓰므로
    fold 를 그대로 반환(decay 만 반환하면 재계산 낭비). 비용은 회전분에만 작용(turnover×bps)이라
    각 비용이 독립 백테스트. liquidity_port(ADR-010)는 전 비용 변동에 동일 주입(필터 일관).
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
            liquidity_port=liquidity_port,
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
    liquidity_port: LiquidityPort,
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
        liquidity_port=liquidity_port,
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
    rule_signature: str  # compute_rule_signature(룰 7필드·cost/start/end 제외) — flip 일치 기준
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
    liquidity_port: LiquidityPort,
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
        liquidity_port=liquidity_port,
    )
    return rerun == f.oos_result


def run_s6_gate(
    config: BacktestConfig,
    *,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    strategy: Strategy,
    liquidity_port: LiquidityPort,
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

    rule_sig = compute_rule_signature(
        strategy_name=config.strategy_name,
        top_n=config.top_n,
        lookback_days=config.lookback_days,
        skip_recent_days=config.skip_recent_days,
        rebalance_freq=config.rebalance_freq,
        delisting_recovery_rate=config.delisting_recovery_rate,
        group_by_exchange=config.group_by_exchange,
        period_return_cap=config.period_return_cap,  # 비정규 cap(env override) 게이트는 flip 불가
    )
    if not verify_passed:
        # G-7 무결성 실패 → 데이터 신뢰 불가. 손상 데이터 백테스트(G-1~G-6)는 garbage-in·무의미.
        # 단락: 비싼 백테스트 미실행·passed=false 기록(전 G AND 라 G-7 하나로 확정·OOM/8hr 회피).
        logger.error("G-7 무결성 실패 — 데이터 신뢰 불가·백테스트 미실행(validated=false 확정)")
        result = evaluate_criteria(
            rule_signature=rule_sig,
            fold_decays=(),
            fold_is_failed=(),
            n_folds=0,
            oos_excesses=(),
            delisted_ratio=delisted_ratio,
            n_delisted_liquidations=0,
            sensitivity={},
            verify_passed=False,
            reproducible=False,
        )
        return replace(
            result,
            notes=(
                *result.notes,
                "G-7 무결성 실패 → 백테스트 미실행(데이터 신뢰 불가·garbage-in 방지)",
            ),
        )

    by_cost = walk_forward_by_cost(
        config,
        price_port=price_port,
        universe_port=universe_port,
        identity=identity,
        strategy=strategy,
        liquidity_port=liquidity_port,
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
            liquidity_port=liquidity_port,
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
        liquidity_port=liquidity_port,
    )

    result = evaluate_criteria(
        rule_signature=rule_sig,
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


# 게이트가 검증하는 룰의 정규 실행 파라미터 — ranking(실행 파라미터 미노출)이 signature 구성에 사용.
# CLI(Task4)도 동일 값으로 config 를 만들어야 ranking 매칭 가능(불일치=보수적 false).
_CANONICAL_STRATEGY_NAME = "equal_weight_top_n"
_CANONICAL_REBALANCE_FREQ = "monthly"


def _canonical_recovery_rate() -> Decimal:
    from decimal import Decimal as D

    return D("0")


def compute_rule_signature(
    *,
    strategy_name: str,
    top_n: int,
    lookback_days: int,
    skip_recent_days: int,
    rebalance_freq: str,
    delisting_recovery_rate: Decimal,
    group_by_exchange: bool,
    period_return_cap: Decimal = _DEFAULT_RETURN_CAP,
) -> str:
    """검증된 **룰 정체성** 해시 — gate 기록과 route 요청이 같은 룰이면 같은 키.

    cost_bps(G-6 가 5/10/15 범위로 검증 — 룰 정체성 아님)·start/end(백테스트 window·룰 아님)는
    **제외**. 8개 필드가 "어떤 룰을 검증했나"를 규정한다. recovery 는 Decimal→normalize 문자열.
    period_return_cap(L4 상한)은 수익 계산식을 바꾸므로 포함 — 기본값=정규 동결값. route/ranking 은
    인자 생략 시 정규 cap 매칭, 비정규 cap 게이트는 signature 불일치라 flip 안 됨.
    """
    payload = {
        "strategy_name": strategy_name,
        "top_n": top_n,
        "lookback_days": lookback_days,
        "skip_recent_days": skip_recent_days,
        "rebalance_freq": rebalance_freq,
        "delisting_recovery_rate": f"{delisting_recovery_rate.normalize():f}",
        "group_by_exchange": group_by_exchange,
        "period_return_cap": f"{period_return_cap.normalize():f}",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def write_s6_gate_result(base_dir: Path, result: S6GateResult) -> Path:
    """게이트 판정을 base_dir/s6_gate_result.json 에 원자 기록(flip 단일 진실원천). 반환=경로.

    원자: temp→os.replace(반쪽 부패 방지). 전 기준·측정값 직렬화(Task5 리포트·감사). flip 은
    passed+rule_signature 만 읽지만, 정직한 판정 추적 위해 per-G·notes·민감도 전부 보존.
    """
    payload = {
        "passed": result.passed,
        "rule_signature": result.rule_signature,
        "n_folds": result.n_folds,
        "criteria": {
            "G-1_is": result.g1_is_pass,
            "G-2_decay": result.g2_decay_pass,
            "G-3_excess": result.g3_excess_pass,
            "G-4_nfolds": result.g4_nfolds_pass,
            "G-5_delisted": result.g5_delisted_pass,
            "G-6_cost": result.g6_cost_pass,
            "G-7_verify": result.g7_verify_pass,
            "G-8_reproducible": result.g8_reproducible,
        },
        "fold_decays": list(result.fold_decays),
        "sensitivity": result.sensitivity,
        "delisted_ratio": result.delisted_ratio,
        "n_delisted_liquidations": result.n_delisted_liquidations,
        "oos_excesses": list(result.oos_excesses),
        "notes": list(result.notes),
    }
    path = base_dir / _RESULT_NAME
    tmp = base_dir / (_RESULT_NAME + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    logger.info("S6-b 게이트 결과 기록: passed=%s → %s", result.passed, path)
    return path


def load_s6_gate_verdict(base_dir: Path, request_signature: str) -> bool:
    """validated 판정 — 파일 존재 AND signature 일치 AND passed=True 만 True. 그 외 전부 False.

    보수(BLOCKING): 부재(게이트 미실행)·signature 불일치(검증 안 된 다른 룰)·passed=False·파싱오류
    모두 False — 미검증을 검증으로 오인 금지(meta.validated=false 가 기본·§4.1).
    """
    path = base_dir / _RESULT_NAME
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("s6_gate_result.json 읽기/파싱 실패 — validated=false(보수)")
        return False
    if not isinstance(payload, dict):
        return False
    # `is True` — 손상/수기편집 JSON 의 "false"(문자열)·1 등 truthy 오판 차단(검증 누수 0·보수).
    return payload.get("passed") is True and payload.get("rule_signature") == request_signature


def ranking_rule_signature(
    *,
    top_n: int,
    lookback_days: int,
    skip_recent_days: int,
    group_by_exchange: bool,
) -> str:
    """ranking(실행 파라미터 미노출)용 룰 signature — strategy/rebalance/recovery 를 게이트 정규값
    으로 채워 compute_rule_signature 에 위임. 게이트가 정규 실행으로 검증했고 모멘텀 파라미터
    (lookback/skip/top_n/group)가 일치하면 매칭, 그 외엔 보수적 false(검증 안 된 실행).
    """
    return compute_rule_signature(
        strategy_name=_CANONICAL_STRATEGY_NAME,
        top_n=top_n,
        lookback_days=lookback_days,
        skip_recent_days=skip_recent_days,
        rebalance_freq=_CANONICAL_REBALANCE_FREQ,
        delisting_recovery_rate=_canonical_recovery_rate(),
        group_by_exchange=group_by_exchange,
    )


def canonical_gate_config(
    *,
    start: date,
    end: date,
    top_n: int = 5,
    lookback_days: int = 126,
    skip_recent_days: int = 21,
    group_by_exchange: bool = False,
) -> BacktestConfig:
    """게이트가 검증하는 **정규 룰 config** — 실행 파라미터를 동결값으로 채운 단일 출처.

    strategy=equal_weight_top_n·rebalance=monthly·cost=baseline(10)·recovery=0·group_by_exchange=False.
    CLI(Task4)는 반드시 이 팩토리로 config 를 만들어야 route 의 `compute_rule_signature`/
    `ranking_rule_signature` 와 같은 키가 나와 flip 이 일관된다(정규값 발산=영원히 false 함정 방지).
    ⚠️ group_by_exchange 기본 False(평면 랭킹) — ranking `group=all` 과 매칭. `group=exchange`(기본
    True)는 정규 config 와 불일치라 보수적 false(원하면 게이트를 group_by_exchange=True 로 재실행).
    """
    from .config import BacktestConfig as _Config

    return _Config(
        strategy_name=_CANONICAL_STRATEGY_NAME,
        top_n=top_n,
        lookback_days=lookback_days,
        skip_recent_days=skip_recent_days,
        rebalance_freq=_CANONICAL_REBALANCE_FREQ,
        cost_bps=_baseline_cost(),
        delisting_recovery_rate=_canonical_recovery_rate(),
        group_by_exchange=group_by_exchange,
        start=start,
        end=end,
    )


def _verify_gate(base_dir: Path) -> bool:
    """G-7 — verify_parquet 무결성(예외 격리). VerificationError/실패 → False(데이터 신뢰 불가).

    ⚠️ 대용량(5.1G)서 ≥수백초. zero-adjusted(adj_factor=0) 다수면 여기서 fail = 데이터 품질 블로커
    (정직히 validated=false). verify 실패는 게이트 fail 로 흡수(전체 중단보다 정직·bulk 와 동형).
    """
    from ..data.storage import VerificationError, verify_parquet

    try:
        report = verify_parquet(base_dir)
    except VerificationError:
        logger.error(
            "G-7 무결성 verify 실패 — 데이터 신뢰 불가(zero-adjusted 등 조사)", exc_info=True
        )
        return False
    return report.passed


def _print_verdict(result: S6GateResult) -> None:
    """판정 결과 사람용 출력(print — CLI 진입점 예외·logging-rules)."""
    criteria = (
        ("G-1 IS성과", result.g1_is_pass),
        ("G-2 OOS방어", result.g2_decay_pass),
        ("G-3 벤치초과", result.g3_excess_pass),
        ("G-4 분할수", result.g4_nfolds_pass),
        ("G-5 폐지커버", result.g5_delisted_pass),
        ("G-6 비용민감", result.g6_cost_pass),
        ("G-7 무결성", result.g7_verify_pass),
        ("G-8 재현성", result.g8_reproducible),
    )
    print("[s6_gate] ===== S6-b 신뢰성 게이트 판정 =====")  # noqa: T201
    for label, ok in criteria:
        print(f"[s6_gate]   {'PASS' if ok else 'FAIL'}  {label}")  # noqa: T201
    worst = min(result.oos_excesses) if result.oos_excesses else None
    print(  # noqa: T201
        f"[s6_gate] n_folds={result.n_folds} delisted_ratio={result.delisted_ratio:.3f} "
        f"n_delisted={result.n_delisted_liquidations} worst_oos_excess={worst}"
    )
    print(f"[s6_gate] sensitivity={result.sensitivity}")  # noqa: T201
    verdict = "PASSED → validated=true 가능" if result.passed else "FAILED → validated=false 유지"
    print(f"[s6_gate] 종합: {verdict}")  # noqa: T201
    if result.notes:
        print(f"[s6_gate] notes: {result.notes}")  # noqa: T201


def main(argv: list[str] | None = None) -> int:
    """S6-b 게이트 CLI(격리·~8hr) — verify(G-7) → 전구간 게이트 → s6_gate_result.json → 판정 출력.

    ⚠️ app 정지 후 일회성 컨테이너로 격리(상주 uvicorn 과 메모리 경쟁 OOM·CLAUDE.md 벌크 규약).
    `python -m stockpick.backtest.s6_gate`. base_dir=STOCKPICK_DATA_DIR(기본 data/parquet).
    """
    import argparse

    from ..data import configure_logging
    from .adapters import (
        MasterUniverse,
        _close_liquidity_port,
        _close_price_port,
        _select_liquidity_port,
        _select_price_port,
        _select_universe,
    )
    from .identity import EdgarSnapshotResolver
    from .strategy import EqualWeightTopN

    configure_logging()
    parser = argparse.ArgumentParser(prog="stockpick.backtest.s6_gate")
    parser.add_argument(
        "--n-folds",
        type=int,
        default=_N_FOLDS,
        help="워크포워드 분할 수(G-4 는 >=10 강제·스모크용 축소 가능)",
    )
    parser.add_argument(
        "--skip-verify", action="store_true", help="G-7 verify 생략(스모크용·verify_passed=False)"
    )
    args = parser.parse_args(argv)

    base_dir = Path(os.environ.get("STOCKPICK_DATA_DIR", "data/parquet"))
    logger.info("S6-b 게이트 시작: base_dir=%s, n_folds=%d", base_dir, args.n_folds)

    # 이전 판정 즉시 무효화 — 8hr 실행이 중간 크래시해도 stale verdict(특히 passed:true)가
    # 잔존해 검증으로 오인되는 일 방지(부재→load_verdict false·보수). 완주 시 끝에서 재기록.
    stale = base_dir / _RESULT_NAME
    if stale.is_file():
        stale.unlink()
        logger.info("이전 s6_gate_result.json 무효화(재실행·크래시 안전)")

    verify_passed = False if args.skip_verify else _verify_gate(base_dir)

    price_port = _select_price_port(base_dir)
    try:
        days = price_port.trading_days()
        if not days:
            print("[s6_gate] 데이터 없음 — 종료(먼저 수집·`bulk --finalize`)")  # noqa: T201
            return 1
        universe = _select_universe(base_dir, price_port)
        if isinstance(universe, MasterUniverse):
            delisted_ratio = universe.delisted_ratio()
        else:
            # 스냅샷 부재 → 생존편향 미방어 유니버스. G-5 fail 로 정직히 차단(조용한 통과 금지).
            logger.warning(
                "유니버스 MasterUniverse 아님(생존편향 미방어) — delisted_ratio=0(G-5 fail)"
            )
            delisted_ratio = 0.0
        config = canonical_gate_config(start=days[0], end=days[-1])
        # 유동성 포트(ADR-010) — cache.duckdb(volume) 기반. 부재면 Noop(필터 off·WARNING·H2 거짓PASS
        # 위험) → CLI 는 `bulk --finalize` 로 cache 선행 전제. 끝나면 close(연결 해제).
        liquidity = _select_liquidity_port(
            base_dir,
            min_price=config.min_price_floor,
            min_adv=config.min_adv_dollar,
            window=config.adv_window_days,
        )
        try:
            result = run_s6_gate(
                config,
                price_port=price_port,
                universe_port=universe,
                identity=EdgarSnapshotResolver(base_dir),
                strategy=EqualWeightTopN(),
                liquidity_port=liquidity,
                delisted_ratio=delisted_ratio,
                verify_passed=verify_passed,
                n_folds=args.n_folds,
            )
        finally:
            _close_liquidity_port(liquidity)
    finally:
        _close_price_port(price_port)

    write_s6_gate_result(base_dir, result)
    _print_verdict(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
