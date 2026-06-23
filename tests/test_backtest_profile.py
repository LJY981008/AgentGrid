"""PhaseProfile 계측 결과불변(관측성 Task1·BLOCKING).

phase 계측(`profile` 주입)이 백테스트 **결과를 바꾸지 않음**을 봉인한다 — `profile=None` 과
`PhaseTimer()` 실행이 phase_profile 외 전 필드 bit-identical(equity·지표·n_delisted). phase
키·counts 도 확인(rank/hold_load/hold_return·members/bench_hold). 라이브 0(Fake 포트).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from stockpick.backtest.benchmark import equal_weight_universe
from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import run
from stockpick.backtest.fakes import (
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.profile_types import PhaseTimer
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.rules._scan import PricePoint


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _scenario() -> tuple[
    dict[str, list[PricePoint]],
    BacktestConfig,
    FakeUniversePort,
    StubIdentityResolver,
    EqualWeightTopN,
]:
    days = _weekdays(date(2024, 1, 1), 50)
    series: dict[str, list[PricePoint]] = {
        "A": [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)],
        "B": [PricePoint(d, Decimal(50 + i)) for i, d in enumerate(days)],
        "C": [PricePoint(d, Decimal(120 + i)) for i, d in enumerate(days) if d.day != 20],
    }
    cfg = BacktestConfig(
        strategy_name="equal_weight_top_n",
        top_n=2,
        lookback_days=10,
        skip_recent_days=2,
        rebalance_freq="monthly",
        cost_bps=Decimal("0"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
        start=days[0],
        end=days[-1],
    )
    uni = FakeUniversePort(listed={t: date(2023, 1, 1) for t in series}, delisted={})
    return series, cfg, uni, StubIdentityResolver({}), EqualWeightTopN()


def test_run_profile_result_invariant() -> None:
    """엔진: profile=None vs PhaseTimer() — phase_profile 외 전 필드 bit-identical(BLOCKING)."""
    series, cfg, uni, idn, strat = _scenario()
    r_none = run(
        cfg, price_port=FakePriceSeriesPort(series), universe_port=uni, identity=idn, strategy=strat
    )
    timer = PhaseTimer()
    r_prof = run(
        cfg,
        price_port=FakePriceSeriesPort(series),
        universe_port=uni,
        identity=idn,
        strategy=strat,
        profile=timer,
    )
    assert replace(r_prof, phase_profile=None) == r_none  # 계측이 결과 안 바꿈
    assert r_none.phase_profile is None
    pp = r_prof.phase_profile
    assert pp is not None
    assert {"rank", "hold_load", "hold_return"} <= set(pp.durations)
    assert pp.counts["rank"] == r_prof.n_rebalances  # 리밸당 1회 랭킹
    assert all(v >= 0.0 for v in pp.durations.values())
    assert timer.current_rebalance == r_prof.n_rebalances  # 진행 idx = 리밸 수(루프당 tick)


def test_bench_profile_result_invariant() -> None:
    """벤치: profile=None vs PhaseTimer() — bit-identical + members/bench_hold phase 키."""
    series, cfg, uni, _idn, _strat = _scenario()
    b_none = equal_weight_universe(cfg, price_port=FakePriceSeriesPort(series), universe_port=uni)
    timer = PhaseTimer()
    b_prof = equal_weight_universe(
        cfg, price_port=FakePriceSeriesPort(series), universe_port=uni, profile=timer
    )
    assert replace(b_prof, phase_profile=None) == b_none
    pp = b_prof.phase_profile
    assert pp is not None
    assert {"members", "bench_hold"} <= set(pp.durations)  # 픽스처 매 리밸 멤버≥1
    assert pp.counts["members"] == b_prof.n_rebalances  # members=리밸당 무조건
    assert pp.counts["bench_hold"] <= b_prof.n_rebalances  # bench_hold=members 있을 때만(조건부)


def test_compute_metrics_empty_curve_phase_profile() -> None:
    """빈 equity_curve 분기도 phase_profile 를 positional 전달(필드 순서 결합 봉인)."""
    from stockpick.backtest.metrics import compute_metrics
    from stockpick.backtest.profile_types import PhaseProfile

    pp = PhaseProfile({"rank": 0.1}, {"rank": 1})
    r = compute_metrics(
        [],
        [],
        periods_per_year=12,
        turnover_total=Decimal(0),
        cost_total=Decimal(0),
        n_rebalances=0,
        n_delisted=0,
        benchmark_returns={},
        caveats=(),
        config_fingerprint="x",
        phase_profile=pp,
    )
    assert r.phase_profile is pp  # 빈 곡선에서도 round-trip(positional 순서 정확)


def test_phase_profile_snapshot_peak_fields() -> None:
    """snapshot 의 peak 3종 필드 — 기본 None(profile CLI 가 채움)·주입 시 반영."""
    timer = PhaseTimer()
    timer.observe("rank", 0.5)
    bare = timer.snapshot()
    assert bare.python_peak_bytes is None and bare.rss_peak_bytes is None
    filled = timer.snapshot(python_peak_bytes=100, rss_peak_bytes=200, duckdb_peak_bytes=300)
    assert filled.python_peak_bytes == 100
    assert filled.rss_peak_bytes == 200
    assert filled.duckdb_peak_bytes == 300
    assert filled.durations["rank"] == 0.5
