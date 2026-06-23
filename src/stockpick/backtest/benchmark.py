"""벤치마크 곡선 — 등가중 전체 유니버스(폐지 포함·공정 비교군).

룰이 등가중 유니버스를 못 이기면 종목 선택이 무가치(생존편향 안전 — 룰과 동일 UniversePort 사용).
엔진과 동일한 forward-return·폐지청산·룩어헤드(진입 t+1) 회계를 재사용한다. S&P500 historical
constituents 벤치는 생존편향 없는 지수 재구성이 필요해 결제 후(후속).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

from . import calendar
from .engine import _holding_period_return, _window_start
from .metrics import compute_metrics

if TYPE_CHECKING:
    from datetime import date

    from .config import BacktestConfig
    from .metrics import BacktestResult
    from .ports import PriceSeriesPort, UniversePort

logger = logging.getLogger(__name__)

_PERIODS_PER_YEAR = {"monthly": 12, "quarterly": 4}
_BENCH_CAVEAT = (
    "벤치=등가중 전체 유니버스(폐지 포함·무비용=이론 상한). ⚠️ 멤버=거래가능 전체"
    "(룰은 모멘텀 산출가능 top_n — 워밍업 구간 풀 상이) · 키=ticker(cik 앵커 아님, "
    "ticker_history 도입 후 정규화). S&P500 historical constituents 는 후속(결제 후)."
)


def equal_weight_universe(
    config: BacktestConfig,
    *,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
) -> BacktestResult:
    """매 리밸 as_of=t 거래가능 종목 전체를 등가중 보유 → 벤치 자산곡선. 룰과 동일 회계.

    멤버십은 `tickers_with_data`(DISTINCT ticker·가격 미물질화·Task7 최적화), 보유수익은 보유종목
    × [entry,exit] 만 `load_range`(full_series·load(as_of) 전체 OOM 회피).
    ⚠️ members 판정은 [_window_start(t), t] 가격존재 — 갭 없는 정상 종목은 load(as_of) 전체와 동일
    (결과 불변), 장기 거래정지 종목은 발산 가능(C1 계열·드묾·실데이터 측정).
    """
    plan = calendar.holding_periods(
        price_port.trading_days(),
        start=config.start,
        end=config.end,
        freq=config.rebalance_freq,
    )

    equity = Decimal(1)
    curve: list[tuple[date, Decimal]] = []
    period_returns: list[Decimal] = []
    n_delisted = 0
    if plan.anchor is not None:
        curve.append((plan.anchor, equity))

    for t, entry_day, exit_day in plan.periods:
        tradable = universe_port.constituents(as_of=t)
        # 멤버십만 필요(가격 미사용) — load_range PricePoint 물질화 회피·키집합 동치(Task7 finding).
        members = price_port.tickers_with_data(
            tickers=tradable, start=_window_start(config, t), end=t
        )
        if members:
            w = Decimal(1) / Decimal(len(members))
            weights = {tk: w for tk in members}
            key_to_ticker = {tk: tk for tk in members}
            held = price_port.load_range(tickers=members, start=entry_day, end=exit_day)
            pret, delisted, _ = _holding_period_return(
                weights,
                key_to_ticker,
                held,
                entry_day,
                exit_day,
                universe_port,
                config.delisting_recovery_rate,
            )
        else:
            pret, delisted = Decimal(0), 0
        n_delisted += delisted
        equity *= Decimal(1) + pret
        period_returns.append(pret)
        curve.append((exit_day, equity))

    logger.info("벤치(등가중 유니버스) 완료: 기간=%d, 폐지청산=%d", len(period_returns), n_delisted)
    return compute_metrics(
        curve,
        period_returns,
        periods_per_year=_PERIODS_PER_YEAR[config.rebalance_freq],
        turnover_total=Decimal(0),
        cost_total=Decimal(0),
        n_rebalances=len(period_returns),
        n_delisted=n_delisted,
        benchmark_returns={},
        caveats=(_BENCH_CAVEAT,),
        config_fingerprint=config.fingerprint(),
    )


def attach_benchmarks(
    result: BacktestResult, benchmarks: dict[str, BacktestResult]
) -> BacktestResult:
    """전략 결과에 벤치 총수익(float)을 주입(frozen → replace). 초과수익 비교용."""
    return replace(
        result,
        benchmark_returns={name: float(b.total_return) for name, b in benchmarks.items()},
    )
