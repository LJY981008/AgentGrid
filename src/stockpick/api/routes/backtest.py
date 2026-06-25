"""GET /api/backtest — 룰 백테스트(골격) 자산곡선·지표·벤치.

엔진(backtest/)을 HTTP 로 노출. demo.run_demo 와 동일 조합이나 print 아니라 JSON 을 돌려준다.
조합: ParquetPriceSeriesPort → PriceDerivedUniverse(가격기반·survivorship 한계)
→ StubIdentityResolver → 전략 → BacktestConfig → engine.run → equal_weight_universe(벤치) → attach.

⭐ §4.1 BLOCKING: meta.validated=false + warning 을 **항상** 포함(골격·미검증 — 알파 아님). 데이터
없음·정상 산출 모두 warning 유지. data_caveats(엔진 산출)로 골격 한계(가격기반 유니버스·cik 미해소·
구간 짧음)를 프론트에 명시 고지.

⚠️ 과적합 노브 최소화: 쿼리는 strategy·top_n·rebalance_freq 만. lookback·skip·cost·recovery 는
서버 고정(사용자가 "예쁜 결과" 나올 때까지 튜닝 못 하게). 파라미터 위반은 Query 제약으로 422.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, Query

from ...backtest.adapters import (
    _close_liquidity_port,
    _close_price_port,
    _select_liquidity_port,
    _select_price_port,
    _select_universe,
)
from ...backtest.benchmark import attach_benchmarks, equal_weight_universe
from ...backtest.config import BacktestConfig
from ...backtest.engine import run as run_backtest
from ...backtest.s6_gate import compute_rule_signature, load_s6_gate_verdict
from ...backtest.strategy import EqualWeightTopN, ScoreWeightTopN, Strategy
from ..deps import get_base_dir, get_identity_resolver
from ..models import (
    BacktestMeta,
    BacktestMetrics,
    BacktestParams,
    BacktestResponse,
    EquityPoint,
)

if TYPE_CHECKING:
    from ...backtest.ports import IdentityResolver

logger = logging.getLogger(__name__)

router = APIRouter()

_WARNING = "백테스트 골격 — 미검증(알파 아님). 무료 데이터·가격기반 유니버스 (stock-1st_plan §4.1)"
_WARNING_VALIDATED = "S6-b 신뢰성 게이트 통과(OOS 강건성 검증) — 과거 성과는 미래 보장 아님"
_STRATEGIES: dict[str, Strategy] = {
    "equal_weight": EqualWeightTopN(),
    "score_weight": ScoreWeightTopN(),
}
# 서버 고정(과적합 노브 최소화) — demo.run_demo 와 동일 기본값.
_LOOKBACK_DAYS = 126
_SKIP_RECENT_DAYS = 21
_COST_BPS = Decimal("10")
_RECOVERY_RATE = Decimal("0")


@router.get("/backtest", response_model=BacktestResponse)
def backtest(
    base_dir: Path = Depends(get_base_dir),
    strategy: Literal["equal_weight", "score_weight"] = Query(
        default="equal_weight", description="포트폴리오 전략"
    ),
    top_n: int = Query(default=5, ge=1, description="보유 종목 수(Top N)"),
    rebalance_freq: Literal["monthly", "quarterly"] = Query(
        default="monthly", description="리밸런싱 주기"
    ),
    identity: IdentityResolver = Depends(get_identity_resolver),
) -> BacktestResponse:
    params = BacktestParams(
        strategy=strategy,
        top_n=top_n,
        rebalance_freq=rebalance_freq,
        lookback_days=_LOOKBACK_DAYS,
        skip_recent_days=_SKIP_RECENT_DAYS,
        cost_bps=float(_COST_BPS),
        delisting_recovery_rate=float(_RECOVERY_RATE),
    )

    # cache.duckdb 있으면 DuckDBPriceSeriesPort(가속)·없으면 Parquet 폴백(결과 동일). 끝나면 close.
    price_port = _select_price_port(base_dir)
    try:
        days = price_port.trading_days()
        if not days:
            # 데이터 없음 → 빈 곡선·0 지표, warning 유지(200 — 첫 실행 정상 상태, 에러 아님).
            logger.info("backtest: Parquet 트리 비어있음 — 빈 백테스트 반환")
            return _empty_response(params)

        universe = _select_universe(base_dir, price_port)
        config = BacktestConfig(
            strategy_name=_STRATEGIES[strategy].name,
            top_n=top_n,
            lookback_days=_LOOKBACK_DAYS,
            skip_recent_days=_SKIP_RECENT_DAYS,
            rebalance_freq=rebalance_freq,
            cost_bps=_COST_BPS,
            delisting_recovery_rate=_RECOVERY_RATE,
            group_by_exchange=False,
            start=days[0],
            end=days[-1],
        )
        # 유동성 포트(ADR-010) — cache 있으면 DuckDB·없으면 Noop(필터 off·WARNING). 요청당 생성.
        liquidity = _select_liquidity_port(
            base_dir,
            min_price=config.min_price_floor,
            min_adv=config.min_adv_dollar,
            window=config.adv_window_days,
        )
        try:
            result = run_backtest(
                config,
                price_port=price_port,
                universe_port=universe,
                identity=identity,  # EdgarSnapshotResolver(저장본 없으면 빈 맵→cik="" 폴백)
                strategy=_STRATEGIES[strategy],
                liquidity_port=liquidity,
            )
            bench = equal_weight_universe(
                config,
                price_port=price_port,
                universe_port=universe,
                liquidity_port=liquidity,
            )
        finally:
            _close_liquidity_port(liquidity)
        result = attach_benchmarks(result, {"EQUAL_WEIGHT_UNIVERSE": bench})
    finally:
        _close_price_port(price_port)  # DuckDB read_only 연결 해제(요청당 생성·누수 방지)

    # validated flip(S6-b) — 이 룰이 게이트 통과·signature 일치할 때만 true(그 외 false 보수).
    validated = load_s6_gate_verdict(
        base_dir,
        compute_rule_signature(
            strategy_name=_STRATEGIES[strategy].name,
            top_n=top_n,
            lookback_days=_LOOKBACK_DAYS,
            skip_recent_days=_SKIP_RECENT_DAYS,
            rebalance_freq=rebalance_freq,
            delisting_recovery_rate=_RECOVERY_RATE,
            group_by_exchange=False,
        ),
    )

    return BacktestResponse(
        equity_curve=[EquityPoint(date=d, value=float(v)) for d, v in result.equity_curve],
        benchmark_curve=[EquityPoint(date=d, value=float(v)) for d, v in bench.equity_curve],
        metrics=BacktestMetrics(
            total_return=float(result.total_return),
            cagr=result.cagr,
            sharpe=result.sharpe,
            sortino=result.sortino,
            max_drawdown=result.max_drawdown,
            turnover=float(result.turnover),
            total_cost=float(result.total_cost),
            n_rebalances=result.n_rebalances,
            n_delisted_liquidations=result.n_delisted_liquidations,
        ),
        benchmark_returns=result.benchmark_returns,
        meta=BacktestMeta(
            validated=validated,
            warning=_WARNING_VALIDATED if validated else _WARNING,
            params=params,
            data_caveats=list(result.data_caveats),
        ),
    )


def _empty_response(params: BacktestParams) -> BacktestResponse:
    """데이터 없음 — 빈 곡선·0 지표. validated=false·warning 유지(조용한 추측 금지)."""
    return BacktestResponse(
        equity_curve=[],
        benchmark_curve=[],
        metrics=BacktestMetrics(
            total_return=0.0,
            cagr=0.0,
            sharpe=0.0,
            sortino=0.0,
            max_drawdown=0.0,
            turnover=0.0,
            total_cost=0.0,
            n_rebalances=0,
            n_delisted_liquidations=0,
        ),
        benchmark_returns={},
        meta=BacktestMeta(
            validated=False,
            warning=_WARNING,
            params=params,
            data_caveats=["데이터 없음 — 먼저 수집(`python -m stockpick.data.ingest`)"],
        ),
    )
