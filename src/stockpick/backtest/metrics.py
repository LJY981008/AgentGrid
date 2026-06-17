"""백테스트 결과 계약 + 지표. 돈/수익=Decimal, 통계(Sharpe·Sortino·CAGR·MDD)=float 1곳 격리."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


@dataclass(frozen=True, slots=True)
class BacktestResult:
    config_fingerprint: str
    equity_curve: list[tuple[date, Decimal]]
    total_return: Decimal
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    turnover: Decimal
    total_cost: Decimal
    n_rebalances: int
    n_delisted_liquidations: int  # 폐지 청산 건수(생존편향 가드 발동 증거)
    benchmark_returns: dict[str, float]
    data_caveats: tuple[str, ...]  # 미검증 한계(cik미해소·합성폐지·1년치 등)


@dataclass(frozen=True, slots=True)
class GuardReport:
    is_sharpe: float
    oos_sharpe: float
    decay_ratio: float | None  # IS_sharpe<=ε 면 None(분모 폭발 방지)
    is_failed: bool  # IS_sharpe<=0 → 룰 기각
    decay_warning: bool  # decay_ratio < 0.5
    purge_gap_days: int
    sensitivity: dict[str, float] = field(default_factory=dict)  # 후속(인터페이스만)
    notes: tuple[str, ...] = ()


def compute_metrics(
    equity_curve: list[tuple[date, Decimal]],
    period_returns: list[Decimal],
    *,
    periods_per_year: int,
    turnover_total: Decimal,
    cost_total: Decimal,
    n_rebalances: int,
    n_delisted: int,
    benchmark_returns: dict[str, float],
    caveats: tuple[str, ...],
    config_fingerprint: str,
) -> BacktestResult:
    """자산곡선·기간수익 → 지표. 빈 곡선이면 0 안전값(조용한 추측 금지)."""
    if not equity_curve:
        return BacktestResult(
            config_fingerprint,
            [],
            Decimal("0"),
            0.0,
            0.0,
            0.0,
            0.0,
            turnover_total,
            cost_total,
            n_rebalances,
            n_delisted,
            benchmark_returns,
            caveats,
        )
    start_v = equity_curve[0][1]
    end_v = equity_curve[-1][1]
    total_return = end_v / start_v - Decimal(1) if start_v > 0 else Decimal("0")

    rets = [float(r) for r in period_returns]
    sharpe = _annualized_sharpe(rets, periods_per_year)
    sortino = _annualized_sortino(rets, periods_per_year)
    cagr = _cagr(rets, periods_per_year)
    mdd = _max_drawdown([float(v) for _, v in equity_curve])

    return BacktestResult(
        config_fingerprint,
        equity_curve,
        total_return,
        cagr,
        sharpe,
        sortino,
        mdd,
        turnover_total,
        cost_total,
        n_rebalances,
        n_delisted,
        benchmark_returns,
        caveats,
    )


def _annualized_sharpe(rets: list[float], ppy: int) -> float:
    if len(rets) < 2:
        return 0.0
    sd = statistics.stdev(rets)
    if sd == 0:
        return 0.0
    return (statistics.mean(rets) / sd) * math.sqrt(ppy)


def _annualized_sortino(rets: list[float], ppy: int) -> float:
    if len(rets) < 2:
        return 0.0
    downside = [r for r in rets if r < 0]
    if not downside:
        return 0.0
    dd = math.sqrt(sum(r * r for r in downside) / len(rets))
    if dd == 0:
        return 0.0
    return (statistics.mean(rets) / dd) * math.sqrt(ppy)


def _cagr(rets: list[float], ppy: int) -> float:
    if not rets:
        return 0.0
    growth = 1.0
    for r in rets:
        growth *= 1.0 + r
    if growth <= 0:
        return -1.0
    years = len(rets) / ppy
    return growth ** (1.0 / years) - 1.0 if years > 0 else 0.0


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    mdd = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    return mdd
