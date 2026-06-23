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
from dataclasses import replace
from typing import TYPE_CHECKING

from .validation import walk_forward

if TYPE_CHECKING:
    from decimal import Decimal

    from .config import BacktestConfig
    from .ports import IdentityResolver, PriceSeriesPort, UniversePort
    from .strategy import Strategy
    from .validation import Fold

logger = logging.getLogger(__name__)


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
