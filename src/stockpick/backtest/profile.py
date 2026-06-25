"""풀 백테스트 프로파일 — 라이브 /metrics(RSS·phase 곡선) + 종료시 3종 메모리 Pushgateway round.

격리 실행(app 정지·CLAUDE.md 벌크 규약·11.7GB+12g OOM 회피). 진입점이라 print 허용.

⚠️ **peak 11.7GB 범인 가림**: `rss_peak`(ru_maxrss·전체 프로세스) vs `python_peak`(tracemalloc·
Python 힙)의 **차이가 크면 native(DuckDB C++ 버퍼)**·작으면 Python. + DuckDB memory_limit(cap)·
현재 사용량(post-run·best-effort) 보고. 라이브 곡선은 profiler 컨테이너를 Prometheus 가 scrape.

환경변수: STOCKPICK_DATA_DIR(기본 data/parquet)·PUSHGATEWAY_URL(없으면 push skip)·
STOCKPICK_PROFILE_ROUND(round 라벨·before/after)·STOCKPICK_PROFILE_METRICS_PORT(기본 9100).
"""

from __future__ import annotations

import logging
import os
import resource
import time
import tracemalloc
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily

from ..data import configure_logging
from . import engine
from .adapters import (
    DuckDBPriceSeriesPort,
    _close_liquidity_port,
    _close_price_port,
    _select_liquidity_port,
    _select_price_port,
    _select_universe,
)
from .benchmark import equal_weight_universe
from .config import BacktestConfig
from .identity import EdgarSnapshotResolver
from .profile_types import PhaseTimer
from .strategy import EqualWeightTopN

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import date

    from .ports import PriceSeriesPort
    from .profile_types import PhaseProfile

logger = logging.getLogger(__name__)

_DATA_DIR_ENV = "STOCKPICK_DATA_DIR"
_DEFAULT_DATA_DIR = "data/parquet"


class _LivePhaseCollector:
    """라이브 PhaseTimer → scrape 마다 phase 누적초·진행 리밸 노출(prometheus 커스텀 collector).

    durations 는 격리 복사라 torn read 없음. profiler 컨테이너 /metrics 를 Prometheus 가 scrape →
    25분 실행 중 phase 진행·RSS(ProcessCollector 자동) 곡선.
    """

    def __init__(self, timer: PhaseTimer) -> None:
        self._timer = timer

    def collect(self) -> Iterator[GaugeMetricFamily]:
        g = GaugeMetricFamily(
            "stockpick_backtest_phase_seconds_live", "phase 누적 wall(라이브)", labels=["phase"]
        )
        for name, sec in self._timer.durations.items():
            g.add_metric([name], sec)
        yield g
        p = GaugeMetricFamily("stockpick_backtest_progress_rebalance", "진행 리밸 idx(라이브)")
        p.add_metric([], float(self._timer.current_rebalance))
        yield p


def _build_config(days: list[date]) -> BacktestConfig:
    # API /api/backtest 와 동일 파라미터(lookback126·skip21·top5·monthly·cost10) — 라이브 동치.
    return BacktestConfig(
        strategy_name="equal_weight_top_n",
        top_n=5,
        lookback_days=126,
        skip_recent_days=21,
        rebalance_freq="monthly",
        cost_bps=Decimal("10"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
        start=days[0],
        end=days[-1],
    )


def _duckdb_memory(port: PriceSeriesPort) -> tuple[int | None, str | None]:
    """DuckDB 현재 메모리(post-run·best-effort)+memory_limit(cap 문자열). 비-DuckDB→(None,None).

    ⚠️ post-run 현재값이라 peak 아님 — 범인 가림은 rss_peak vs python_peak 가 1차. memory_limit 이
    무제한/호스트RAM 기반이면 버퍼 ballooning 신호(connect_readonly 캡 후속 후보).
    """
    if not isinstance(port, DuckDBPriceSeriesPort):
        return None, None
    import duckdb

    try:
        used_row = port._con.execute(  # noqa: SLF001 — 프로파일 진단 도구(내부 연결 접근 허용)
            "SELECT sum(memory_usage_bytes) FROM duckdb_memory()"
        ).fetchone()
        lim_row = port._con.execute("SELECT current_setting('memory_limit')").fetchone()
    except duckdb.Error:
        logger.exception("DuckDB 메모리 조회 실패 — None")
        return None, None
    used = int(used_row[0]) if used_row and used_row[0] is not None else None
    limit = str(lim_row[0]) if lim_row and lim_row[0] is not None else None
    return used, limit


def main() -> int:
    configure_logging()
    base_dir = Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))
    round_label = os.environ.get("STOCKPICK_PROFILE_ROUND", "adhoc")
    metrics_port = int(os.environ.get("STOCKPICK_PROFILE_METRICS_PORT", "9100"))
    pushgateway = os.environ.get("PUSHGATEWAY_URL")

    timer = PhaseTimer()
    REGISTRY.register(_LivePhaseCollector(timer))  # 라이브 곡선(+ ProcessCollector 자동 RSS)
    start_http_server(metrics_port)  # profiler /metrics — Prometheus scrape
    logger.info("profile /metrics 노출: port=%d round=%s", metrics_port, round_label)

    tracemalloc.start()
    price_port = _select_price_port(base_dir)
    duckdb_used: int | None = None
    duckdb_limit: str | None = None
    t0 = time.monotonic()
    try:
        if not (base_dir / "stock_snapshot.json").is_file():
            # 스냅샷 없으면 _select_universe→PriceDerivedUniverse.full_series(전구간 OOM 위험·M1).
            # 프로파일 대상이 정확히 OOM 시나리오라 측정 전제가 깨짐 — 운영자 강조.
            print("[profile] ⚠️ snapshot 부재 — full_series OOM 위험. `bulk --finalize` 먼저")  # noqa: T201
        universe = _select_universe(base_dir, price_port)
        days = price_port.trading_days()
        if not days:
            print("[profile] 데이터 없음 — 종료")  # noqa: T201
            tracemalloc.stop()
            return 0
        config = _build_config(days)
        identity = EdgarSnapshotResolver(base_dir)
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
                profile=timer,
            )
            equal_weight_universe(
                config,
                price_port=price_port,
                universe_port=universe,
                liquidity_port=liquidity,
                profile=timer,
            )
        finally:
            _close_liquidity_port(liquidity)
        duckdb_used, duckdb_limit = _duckdb_memory(price_port)
    finally:
        _close_price_port(price_port)
    total_seconds = time.monotonic() - t0

    _python_cur, python_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # KB→bytes(Linux)

    _push_summary(
        pushgateway,
        round_label,
        total_seconds=total_seconds,
        phase=timer.snapshot(python_peak_bytes=python_peak, rss_peak_bytes=rss_peak),
        n_rebalances=result.n_rebalances,
        n_delisted=result.n_delisted_liquidations,
        duckdb_used=duckdb_used,
    )
    print(  # noqa: T201
        f"[profile] round={round_label} wall={total_seconds:.1f}s "
        f"rss_peak={rss_peak / 1e9:.2f}GB python_peak={python_peak / 1e9:.2f}GB "
        f"duckdb_used={'?' if duckdb_used is None else f'{duckdb_used / 1e9:.2f}GB'} "
        f"duckdb_limit={duckdb_limit} phases={timer.durations}",
        flush=True,
    )
    print(  # noqa: T201
        "[profile] 범인 가림: rss_peak >> python_peak 면 native(DuckDB), 비슷하면 Python"
    )
    return 0


def _push_summary(
    pushgateway: str | None,
    round_label: str,
    *,
    total_seconds: float,
    phase: PhaseProfile,
    n_rebalances: int,
    n_delisted: int,
    duckdb_used: int | None,
) -> None:
    """종료 요약을 Pushgateway 에 round 라벨로 push(영속 before/after). URL 없으면 skip."""
    if not pushgateway:
        logger.info("PUSHGATEWAY_URL 없음 — push skip(로컬 측정만)")
        return
    reg = CollectorRegistry()
    Gauge("stockpick_backtest_total_seconds", "풀 백테스트 wall", registry=reg).set(total_seconds)
    g_phase = Gauge("stockpick_backtest_phase_seconds", "phase 누적 wall", ["phase"], registry=reg)
    for name, sec in phase.durations.items():
        g_phase.labels(phase=name).set(sec)
    g_mem = Gauge("stockpick_backtest_peak_bytes", "peak 메모리", ["source"], registry=reg)
    if phase.python_peak_bytes is not None:
        g_mem.labels(source="python").set(phase.python_peak_bytes)
    if phase.rss_peak_bytes is not None:
        g_mem.labels(source="rss").set(phase.rss_peak_bytes)
    if duckdb_used is not None:
        g_mem.labels(source="duckdb").set(duckdb_used)
    Gauge("stockpick_backtest_rebalances_total", "리밸 수", registry=reg).set(n_rebalances)
    Gauge("stockpick_backtest_delisted_total", "폐지 청산", registry=reg).set(n_delisted)
    push_to_gateway(
        pushgateway, job="backtest_profile", grouping_key={"round": round_label}, registry=reg
    )
    logger.info("Pushgateway push 완료: round=%s", round_label)


if __name__ == "__main__":
    raise SystemExit(main())
