"""과적합 가드 — IS/OOS 분할·워크포워드·purge gap·성과방어율(decay).

decay = OOS_sharpe/IS_sharpe. IS<=0 → 룰 기각(is_failed), |IS|<ε → 신호미약(None, 분모 폭발 방지).
워크포워드: IS 창에서 선택·동결 → OOS 검증. 창 경계에 **purge gap**(기본 lookback+skip 거래일)을
두어 OOS 룩백이 IS 를 침범하는 누수를 차단(de Prado purging). 민감도는 후속(인터페이스만).

⚠️ 골격(무료 1년치)에선 리밸 수가 적어 fold 통계는 미검증 — 분할·purge **로직**만 봉인(합성 검증).
수치 신뢰는 결제 후 다년 데이터(S6 게이트 후).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from .engine import run
from .metrics import GuardReport

if TYPE_CHECKING:
    from datetime import date

    from .config import BacktestConfig
    from .metrics import BacktestResult
    from .ports import IdentityResolver, PriceSeriesPort, UniversePort
    from .strategy import Strategy


@dataclass(frozen=True, slots=True)
class Fold:
    """워크포워드 한 fold — IS(선택)·OOS(검증) 구간 결과 + 과적합 가드."""

    index: int
    is_start: date
    is_end: date
    oos_start: date
    oos_end: date
    is_result: BacktestResult
    oos_result: BacktestResult
    guard: GuardReport


def decay_ratio(
    *,
    is_sharpe: float,
    oos_sharpe: float,
    epsilon: float = 0.1,
    warn_below: float = 0.5,
    purge_gap_days: int = 0,
) -> GuardReport:
    """성과방어율 OOS/IS. IS<=0 → 기각(분모 무의미), |IS|<ε → 신호미약(None), 그 외 비율 산출."""
    if is_sharpe <= 0:
        return GuardReport(
            is_sharpe,
            oos_sharpe,
            None,
            is_failed=True,
            decay_warning=False,
            purge_gap_days=purge_gap_days,
            notes=("IS Sharpe<=0 — 룰 IS 자체 실패, 기각",),
        )
    if is_sharpe < epsilon:
        return GuardReport(
            is_sharpe,
            oos_sharpe,
            None,
            is_failed=False,
            decay_warning=False,
            purge_gap_days=purge_gap_days,
            notes=("IS 신호 미약(|IS|<ε) — 비율 무의미",),
        )
    ratio = oos_sharpe / is_sharpe
    return GuardReport(
        is_sharpe,
        oos_sharpe,
        ratio,
        is_failed=False,
        decay_warning=ratio <= warn_below,  # "이하"면 경고(0.5 포함 — 과적합 의심)
        purge_gap_days=purge_gap_days,
    )


def walk_forward(
    config: BacktestConfig,
    *,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    strategy: Strategy,
    n_folds: int = 3,
    purge_gap_days: int | None = None,
) -> list[Fold]:
    """앵커드 워크포워드 — 구간을 (n_folds+1) 등분, fold k = IS[0:경계-purge] / OOS[경계:다음경계].

    purge_gap_days 기본 = lookback_days + skip_recent_days(OOS 룩백이 IS 침범 차단). IS 길이가
    부족한 fold(lookback 미만)는 건너뛴다(조용한 추측 금지 — 빈 fold 생성 안 함).
    """
    if n_folds < 1:
        msg = f"n_folds 는 1 이상(받음={n_folds})"
        raise ValueError(msg)
    purge = (
        purge_gap_days
        if purge_gap_days is not None
        else config.lookback_days + config.skip_recent_days
    )
    days = [d for d in price_port.trading_days() if config.start <= d <= config.end]
    total = len(days)
    seg = total // (n_folds + 1)
    if seg == 0:
        return []  # 데이터가 fold 분할에 부족 — 빈 결과(명시)

    folds: list[Fold] = []
    for k in range(n_folds):
        oos_start_idx = (k + 1) * seg
        oos_end_idx = (k + 2) * seg - 1 if k < n_folds - 1 else total - 1
        is_end_idx = oos_start_idx - purge - 1
        if is_end_idx < config.lookback_days:
            continue  # IS 워밍업 부족 — 이 fold 생략
        is_cfg = replace(config, start=days[0], end=days[is_end_idx])
        oos_cfg = replace(config, start=days[oos_start_idx], end=days[oos_end_idx])
        is_res = run(
            is_cfg,
            price_port=price_port,
            universe_port=universe_port,
            identity=identity,
            strategy=strategy,
        )
        oos_res = run(
            oos_cfg,
            price_port=price_port,
            universe_port=universe_port,
            identity=identity,
            strategy=strategy,
        )
        guard = decay_ratio(
            is_sharpe=is_res.sharpe, oos_sharpe=oos_res.sharpe, purge_gap_days=purge
        )
        folds.append(
            Fold(
                index=k,
                is_start=days[0],
                is_end=days[is_end_idx],
                oos_start=days[oos_start_idx],
                oos_end=days[oos_end_idx],
                is_result=is_res,
                oos_result=oos_res,
                guard=guard,
            )
        )
    return folds
