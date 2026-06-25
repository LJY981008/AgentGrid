"""백테스트 골격 시연 — `data/parquet` → 룰 백테스트 → BacktestResult 출력.

실행: `python -m stockpick.backtest`.

⚠️ 골격 입증용이다(장기 백테스트 아님). 무료 1년치·소수 종목·**합성/제한된 유니버스**(폐지 정보
없음)라 산출 지표는 **검증 전 알파 아님**(stock-1st_plan §4.1). data_caveats 가 한계를 명시한다.
유니버스를 가격 존재로 도출(FakeUniversePort)하므로 생존편향 가드가 실데이터로는 미발동 — 결제 후
종목마스터(listed/delisted)·실폐지·ticker_history(cik) 도입 시 같은 코드로 정식 동작한다.

진입점이라 print 허용(logging-rules 예외). 라이브러리 코드(engine·metrics 등)는 print 없음.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from ..data import configure_logging
from . import engine
from .adapters import (
    _close_liquidity_port,
    _close_price_port,
    _select_liquidity_port,
    _select_price_port,
    _select_universe,
)
from .benchmark import attach_benchmarks, equal_weight_universe
from .config import BacktestConfig
from .identity import EdgarSnapshotResolver
from .strategy import EqualWeightTopN

if TYPE_CHECKING:
    from pathlib import Path

    from .metrics import BacktestResult

logger = logging.getLogger(__name__)


def run_demo(base_dir: Path) -> int:
    """무료 골격 백테스트 1회 실행·출력. 데이터 없으면 안내 후 0(no-op). 반환 = 종료코드."""
    configure_logging()
    # cache.duckdb 있으면 DuckDBPriceSeriesPort(가속)·없으면 Parquet 폴백(결과 동일). 끝나면 close.
    price_port = _select_price_port(base_dir)
    try:
        days = price_port.trading_days()
        if not days:
            print(f"[백테스트 데모] 수집 데이터 없음: {base_dir}/daily_bar")  # noqa: T201
            print("  → 먼저 `python -m stockpick.data.ingest` 로 적재하세요.")  # noqa: T201
            return 0

        universe = _select_universe(base_dir, price_port)  # 스냅샷 있으면 Master·없으면 폴백
        identity = EdgarSnapshotResolver(base_dir)  # EDGAR 저장본 cik(없으면 빈 맵→"")
        config = BacktestConfig(
            strategy_name="equal_weight_top_n",
            top_n=min(5, universe.ticker_count()),
            lookback_days=126,
            skip_recent_days=21,
            rebalance_freq="monthly",
            cost_bps=Decimal("10"),
            delisting_recovery_rate=Decimal("0"),
            group_by_exchange=False,
            start=days[0],
            end=days[-1],
        )
        # 유동성 포트(ADR-010) — cache 있으면 DuckDB·없으면 Noop(필터 off·WARNING). 끝나면 close.
        liquidity = _select_liquidity_port(
            base_dir,
            min_price=config.min_price_floor,
            min_adv=config.min_adv_dollar,
            window=config.adv_window_days,
        )
        try:
            result = engine.run(
                config,
                price_port=price_port,
                universe_port=universe,
                identity=identity,
                strategy=EqualWeightTopN(),
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
        _print_report(result, n_tickers=universe.ticker_count())
    finally:
        _close_price_port(price_port)  # DuckDB read_only 연결 해제
    return 0


def _print_report(result: BacktestResult, *, n_tickers: int) -> None:
    """BacktestResult 콘솔 출력 — 지표 + 미검증 경고 + data_caveats."""
    print("\n=== 백테스트 골격 결과 (⚠️ 검증 전 — 알파 아님) ===")  # noqa: T201
    print(f"  종목 수={n_tickers}  리밸 기간={result.n_rebalances}")  # noqa: T201
    print(f"  폐지청산={result.n_delisted_liquidations}건")  # noqa: T201
    print(f"  총수익={result.total_return:.4f}  CAGR={result.cagr:.4f}")  # noqa: T201
    print(f"  Sharpe={result.sharpe:.3f}  Sortino={result.sortino:.3f}")  # noqa: T201
    print(f"  MDD={result.max_drawdown:.4f}")  # noqa: T201
    print(f"  회전율합={result.turnover:.2f}  총비용={result.total_cost:.4f}")  # noqa: T201
    for name, ret in result.benchmark_returns.items():
        excess = float(result.total_return) - ret
        print(f"  벤치[{name}]={ret:.4f}  초과수익={excess:+.4f}")  # noqa: T201
    print("  ⚠️ data_caveats(미검증 한계):")  # noqa: T201
    for c in result.data_caveats:
        print(f"    - {c}")  # noqa: T201
