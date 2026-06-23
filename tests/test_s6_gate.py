"""S6-b 신뢰성 게이트 테스트 — 비용 민감도·게이트 판정·결과불변(합성 데이터)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import run
from stockpick.backtest.fakes import (
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.metrics import GuardReport, compute_metrics
from stockpick.backtest.s6_gate import (
    _worst_decay,
    sensitivity_analysis,
    walk_forward_by_cost,
)
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.backtest.validation import Fold
from stockpick.rules._scan import PricePoint


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _cfg(days: list[date], **kw: object) -> BacktestConfig:
    base: dict[str, object] = dict(
        strategy_name="equal_weight_top_n",
        top_n=1,
        lookback_days=5,
        skip_recent_days=0,
        rebalance_freq="monthly",
        cost_bps=Decimal("0"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
        start=days[0],
        end=days[-1],
    )
    base.update(kw)
    return BacktestConfig(**base)  # type: ignore[arg-type]


def _ports() -> tuple[FakePriceSeriesPort, FakeUniversePort, StubIdentityResolver]:
    days = _weekdays(date(2024, 1, 1), 250)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]  # 상승(모멘텀 선택)
    b = [PricePoint(d, Decimal("100")) for d in days]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    return port, uni, ident


def test_sensitivity_analysis_has_key_per_cost_variant() -> None:
    port, uni, ident = _ports()
    days = port.trading_days()
    result = sensitivity_analysis(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        n_folds=2,
        purge_gap_days=5,
    )
    # 기본 비용 변동 5/10/15bps 각각 키 존재·값 float
    assert set(result.keys()) == {"5bps", "10bps", "15bps"}
    assert all(isinstance(v, float) for v in result.values())


def test_sensitivity_analysis_is_result_invariant() -> None:
    # 계측이 원 백테스트를 바꾸지 않음 — config(frozen)·ports(read-only) 불변 → run() bit-identical.
    port, uni, ident = _ports()
    days = port.trading_days()
    cfg = _cfg(days)

    def _run() -> object:
        return run(
            cfg, price_port=port, universe_port=uni, identity=ident, strategy=EqualWeightTopN()
        )

    before = _run()
    _ = sensitivity_analysis(
        cfg,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        n_folds=2,
        purge_gap_days=5,
    )
    after = _run()
    assert before == after  # BacktestResult frozen eq — 동일
    assert cfg.cost_bps == Decimal("0")  # 원 config 비용 미변경(replace 신규 객체 사용)


def test_walk_forward_by_cost_threads_distinct_cost_into_each_fold() -> None:
    # 봉인: 각 비용이 fold config 에 실제 주입됐는지 fingerprint 발산으로 결정적 확인.
    # decay 수치는 작은 픽스처서 비용 무관하게 같을 수 있으나, cost_bps 는 fingerprint 구성요소라
    # replace(config, cost_bps=c) 가 빠지면 변동 간 fingerprint 가 동일해져 이 테스트가 실패한다.
    port, uni, ident = _ports()
    days = port.trading_days()
    by_cost = walk_forward_by_cost(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        cost_bps_variants=(Decimal("5"), Decimal("15")),
        n_folds=2,
        purge_gap_days=5,
    )
    assert by_cost[Decimal("5")] and by_cost[Decimal("15")]  # fold 존재(픽스처 충분)
    fp5 = by_cost[Decimal("5")][0].is_result.config_fingerprint
    fp15 = by_cost[Decimal("15")][0].is_result.config_fingerprint
    assert fp5 != fp15  # 동일 fold·다른 비용 → fingerprint 달라야(비용 주입 증거)


def _dummy_result() -> object:
    return compute_metrics(
        [],
        [],
        periods_per_year=12,
        turnover_total=Decimal("0"),
        cost_total=Decimal("0"),
        n_rebalances=0,
        n_delisted=0,
        benchmark_returns={},
        caveats=(),
        config_fingerprint="x",
    )


def _fold(decay: float | None) -> Fold:
    guard = GuardReport(
        is_sharpe=1.0,
        oos_sharpe=(decay if decay is not None else 0.0),
        decay_ratio=decay,
        is_failed=(decay is None),
        decay_warning=False,
        purge_gap_days=0,
    )
    res = _dummy_result()
    return Fold(
        index=0,
        is_start=date(2024, 1, 1),
        is_end=date(2024, 1, 2),
        oos_start=date(2024, 1, 3),
        oos_end=date(2024, 1, 4),
        is_result=res,  # type: ignore[arg-type]
        oos_result=res,  # type: ignore[arg-type]
        guard=guard,
    )


def test_worst_decay_empty_folds_is_zero() -> None:
    # 빈 fold(데이터 부족) → 0.0(fail-closed·G-2 미달).
    assert _worst_decay([]) == 0.0


def test_worst_decay_all_none_is_zero() -> None:
    # 전 fold None(IS<=0 기각/신호미약) → 0.0.
    assert _worst_decay([_fold(None), _fold(None)]) == 0.0


def test_worst_decay_partial_none_sinks_to_zero() -> None:
    # 핵심: 강한 fold(2.0)가 있어도 None 한 개가 최악값을 0.0 으로 끌어내림(보수적 판정).
    assert _worst_decay([_fold(2.0), _fold(None)]) == 0.0


def test_worst_decay_returns_true_min_when_all_valid() -> None:
    # 전 fold 유효 → 진짜 최솟값.
    assert _worst_decay([_fold(2.0), _fold(0.8), _fold(1.5)]) == 0.8
