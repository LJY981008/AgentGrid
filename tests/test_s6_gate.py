"""S6-b 신뢰성 게이트 테스트 — 비용 민감도·게이트 판정·결과불변(합성 데이터)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import run
from stockpick.backtest.fakes import (
    FakeLiquidityPort,
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.metrics import GuardReport, compute_metrics
from stockpick.backtest.s6_gate import (
    _DECAY_MIN,
    _DELISTED_MIN,
    _N_FOLDS,
    S6GateResult,
    _verify_gate,
    _worst_decay,
    canonical_gate_config,
    compute_rule_signature,
    evaluate_criteria,
    load_s6_gate_verdict,
    ranking_rule_signature,
    run_s6_gate,
    sensitivity_analysis,
    walk_forward_by_cost,
    write_s6_gate_result,
)
from stockpick.backtest.s6_gate import main as s6_gate_main
from stockpick.backtest.strategy import EqualWeightTopN, TopDecileEqualWeight
from stockpick.backtest.validation import Fold, walk_forward
from stockpick.data import storage
from stockpick.data.storage import write_daily_bars
from stockpick.rules._scan import PricePoint
from stockpick.types import DailyBar, Exchange

_NOLIQ = FakeLiquidityPort(None)  # 필터 off(전종목 유동) — 게이트 배선·결과불변 검증용


def _pass_kwargs() -> dict[str, object]:
    """evaluate_criteria 전 기준 통과 입력(각 테스트가 한 항목만 뒤집어 단일-FAIL 확인)."""
    return dict(
        rule_signature="sig",
        fold_decays=(0.9,) * 10,
        fold_is_failed=(False,) * 10,
        n_folds=10,
        oos_excesses=(0.05,) * 10,
        delisted_ratio=0.5,
        n_delisted_liquidations=3,
        sensitivity={"5bps": 0.8, "10bps": 0.9, "15bps": 0.7},
        verify_passed=True,
        reproducible=True,
    )


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
        liquidity_port=_NOLIQ,
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
            cfg,
            price_port=port,
            universe_port=uni,
            identity=ident,
            strategy=EqualWeightTopN(),
            liquidity_port=_NOLIQ,
        )

    before = _run()
    _ = sensitivity_analysis(
        cfg,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=_NOLIQ,
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
        liquidity_port=_NOLIQ,
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


# ── Task2: 게이트 판정 로직(evaluate_criteria) — 임계 동결·PASS·단일 FAIL ──


def test_thresholds_are_frozen_module_constants() -> None:
    # 사전 동결(ADR-009) — 데이터로 임계 고르기 금지. 상수 값이 바뀌면 이 테스트가 깨진다.
    assert _DECAY_MIN == 0.5
    assert _N_FOLDS == 10
    assert _DELISTED_MIN == 0.30


def test_evaluate_criteria_all_pass() -> None:
    r = evaluate_criteria(**_pass_kwargs())  # type: ignore[arg-type]
    assert isinstance(r, S6GateResult)
    assert r.passed is True
    assert r.rule_signature == "sig"


def test_evaluate_criteria_g1_fail_when_any_fold_is_failed() -> None:
    kw = _pass_kwargs()
    kw["fold_is_failed"] = (False,) * 9 + (True,)  # IS<=0 fold 1개
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g1_is_pass is False
    assert r.passed is False


def test_evaluate_criteria_g2_fail_when_any_decay_below_min() -> None:
    kw = _pass_kwargs()
    kw["fold_decays"] = (0.9,) * 9 + (0.4,)  # decay<0.5 fold 1개
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g2_decay_pass is False
    assert r.passed is False


def test_evaluate_criteria_g2_fail_when_any_decay_none() -> None:
    kw = _pass_kwargs()
    kw["fold_decays"] = (0.9,) * 9 + (None,)  # 비율 무의미 fold → G-2 미달
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g2_decay_pass is False
    assert r.passed is False


def test_evaluate_criteria_g3_fail_when_any_fold_not_positive() -> None:
    kw = _pass_kwargs()
    kw["oos_excesses"] = (0.5,) * 9 + (0.0,)  # 한 fold 가 등가중 못 이김(>0 아님)
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g3_excess_pass is False
    assert r.passed is False


def test_evaluate_criteria_g3_fail_when_outlier_masks_negative_folds() -> None:
    # 핵심: 한 fold 폭등(+5.0)이 음수 fold(-0.1)를 평균으로 가려선 안 됨 — 전 fold>0 라야 통과.
    kw = _pass_kwargs()
    kw["oos_excesses"] = (5.0,) + (-0.1,) * 9  # 평균은 양수지만 9개 fold 가 벤치 못 이김
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g3_excess_pass is False
    assert r.passed is False


def test_evaluate_criteria_g4_fail_when_too_few_folds() -> None:
    kw = _pass_kwargs()
    kw["n_folds"] = 9  # <10
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g4_nfolds_pass is False
    assert r.passed is False


def test_evaluate_criteria_g5_fail_when_delisted_ratio_low() -> None:
    kw = _pass_kwargs()
    kw["delisted_ratio"] = 0.29  # <30%
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g5_delisted_pass is False
    assert r.passed is False


def test_evaluate_criteria_g5_fail_when_no_liquidations() -> None:
    kw = _pass_kwargs()
    kw["n_delisted_liquidations"] = 0  # 생존편향 가드 死문자
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g5_delisted_pass is False
    assert r.passed is False


def test_evaluate_criteria_g6_fail_when_any_cost_below_min() -> None:
    kw = _pass_kwargs()
    kw["sensitivity"] = {"5bps": 0.8, "10bps": 0.9, "15bps": 0.4}  # 15bps서 취약
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g6_cost_pass is False
    assert r.passed is False


def test_evaluate_criteria_g7_fail_when_verify_failed() -> None:
    kw = _pass_kwargs()
    kw["verify_passed"] = False  # 무결성 verify 실패(zero-adjusted 등)
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g7_verify_pass is False
    assert r.passed is False


def test_evaluate_criteria_g8_fail_when_not_reproducible() -> None:
    kw = _pass_kwargs()
    kw["reproducible"] = False
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g8_reproducible is False
    assert r.passed is False


def test_run_s6_gate_wiring_fails_on_insufficient_folds() -> None:
    # end-to-end 배선: n_folds=2(<_N_FOLDS) → G-4 fail → passed False. 결과불변·sensitivity 3키.
    port, uni, ident = _ports()
    days = port.trading_days()
    cfg = _cfg(days)
    r = run_s6_gate(
        cfg,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=_NOLIQ,
        delisted_ratio=0.5,
        verify_passed=True,
        n_folds=2,
        purge_gap_days=5,
    )
    assert isinstance(r, S6GateResult)
    assert r.g4_nfolds_pass is False
    assert r.passed is False
    assert set(r.sensitivity.keys()) == {"5bps", "10bps", "15bps"}
    assert r.rule_signature  # 비어있지 않음
    assert cfg.cost_bps == Decimal("0")  # 원 config 미변형


def test_run_s6_gate_rejects_variants_without_baseline() -> None:
    # baseline(10bps) 가 변동에 없으면 baseline fold 재사용 불가 → loud fail(조용한 추측 금지).
    port, uni, ident = _ports()
    days = port.trading_days()
    with pytest.raises(ValueError, match="baseline"):
        run_s6_gate(
            _cfg(days),
            price_port=port,
            universe_port=uni,
            identity=ident,
            strategy=EqualWeightTopN(),
            liquidity_port=_NOLIQ,
            delisted_ratio=0.5,
            verify_passed=True,
            n_folds=2,
            cost_bps_variants=(Decimal("5"), Decimal("15")),  # 10 없음
        )


def test_run_s6_gate_rejects_out_of_range_delisted_ratio() -> None:
    # 외부 측정 경계 검증 — 비물리 비율은 G-5 왜곡 전에 loud fail.
    port, uni, ident = _ports()
    days = port.trading_days()
    with pytest.raises(ValueError, match="delisted_ratio"):
        run_s6_gate(
            _cfg(days),
            price_port=port,
            universe_port=uni,
            identity=ident,
            strategy=EqualWeightTopN(),
            liquidity_port=_NOLIQ,
            delisted_ratio=1.5,  # >1
            verify_passed=True,
            n_folds=2,
        )


# ── Task3: validated flip 배선(compute_rule_signature·write/load_s6_gate_verdict) ──


def _sig_kwargs() -> dict[str, object]:
    return dict(
        strategy_name="equal_weight_top_n",
        top_n=5,
        lookback_days=126,
        skip_recent_days=21,
        rebalance_freq="monthly",
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
    )


def _gate_result(*, passed: bool, signature: str) -> S6GateResult:
    return S6GateResult(
        passed=passed,
        rule_signature=signature,
        n_folds=10,
        g1_is_pass=True,
        g2_decay_pass=True,
        g3_excess_pass=True,
        g4_nfolds_pass=True,
        g5_delisted_pass=True,
        g6_cost_pass=True,
        g7_verify_pass=passed,
        g8_reproducible=True,
        r2_measurable=True,
        fold_decays=(0.9,) * 10,
        sensitivity={"5bps": 0.8, "10bps": 0.9, "15bps": 0.7},
        delisted_ratio=0.5,
        n_delisted_liquidations=3,
        oos_excesses=(0.05,) * 10,
        notes=(),
    )


def test_compute_rule_signature_stable_and_sensitive() -> None:
    a = compute_rule_signature(**_sig_kwargs())  # type: ignore[arg-type]
    b = compute_rule_signature(**_sig_kwargs())  # type: ignore[arg-type]
    assert a == b  # 같은 룰 → 같은 키(결정적)
    kw = _sig_kwargs()
    kw["top_n"] = 6
    assert compute_rule_signature(**kw) != a  # type: ignore[arg-type] # 룰 다르면 키 달라야


def test_load_verdict_no_file_is_false(tmp_path: Path) -> None:
    # 파일 부재(현 상태·게이트 미실행) → false(미검증을 검증으로 오인 금지).
    assert load_s6_gate_verdict(tmp_path, "sig") is False


def test_write_then_load_verdict_passed_matching_signature_true(tmp_path: Path) -> None:
    write_s6_gate_result(tmp_path, _gate_result(passed=True, signature="SIG"))
    assert load_s6_gate_verdict(tmp_path, "SIG") is True


def test_load_verdict_signature_mismatch_is_false(tmp_path: Path) -> None:
    # 통과했어도 다른 룰 요청이면 false(검증 범위 = 통과한 그 config 뿐).
    write_s6_gate_result(tmp_path, _gate_result(passed=True, signature="SIG"))
    assert load_s6_gate_verdict(tmp_path, "OTHER") is False


def test_load_verdict_failed_gate_is_false(tmp_path: Path) -> None:
    # signature 일치해도 게이트 실패면 false.
    write_s6_gate_result(tmp_path, _gate_result(passed=False, signature="SIG"))
    assert load_s6_gate_verdict(tmp_path, "SIG") is False


def test_load_verdict_non_dict_json_is_false(tmp_path: Path) -> None:
    # JSON 이 dict 아니면(리스트 등) false(isinstance 가드).
    (tmp_path / "s6_gate_result.json").write_text("[]", encoding="utf-8")
    assert load_s6_gate_verdict(tmp_path, "sig") is False


def test_load_verdict_passed_truthy_string_is_false(tmp_path: Path) -> None:
    # 손상 JSON "passed":"false"(문자열·truthy) 를 검증으로 오판하면 안 됨 — is True 라야 통과.
    (tmp_path / "s6_gate_result.json").write_text(
        '{"passed": "false", "rule_signature": "SIG"}', encoding="utf-8"
    )
    assert load_s6_gate_verdict(tmp_path, "SIG") is False


def _sig_from_config(cfg: BacktestConfig) -> str:
    # config 전 룰필드 → compute_rule_signature(게이트가 run_s6_gate 에서 쓰는 것과 동일 구성).
    return compute_rule_signature(
        strategy_name=cfg.strategy_name,
        top_n=cfg.top_n,
        lookback_days=cfg.lookback_days,
        skip_recent_days=cfg.skip_recent_days,
        rebalance_freq=cfg.rebalance_freq,
        delisting_recovery_rate=cfg.delisting_recovery_rate,
        group_by_exchange=cfg.group_by_exchange,
        period_return_cap=cfg.period_return_cap,
        portfolio_pct=cfg.portfolio_pct,
        decile_min_holdings=cfg.decile_min_holdings,
        min_price_floor=cfg.min_price_floor,
        min_adv_dollar=cfg.min_adv_dollar,
        adv_window_days=cfg.adv_window_days,
    )


def test_compute_rule_signature_includes_portfolio_and_liquidity_fields() -> None:
    # 신규 동결 필드(decile·유동성)는 룰 정체성 → signature 발산(동결 우회 차단·ADR-010).
    base = _sig_kwargs()
    a = compute_rule_signature(**base)  # type: ignore[arg-type]
    assert compute_rule_signature(**base, portfolio_pct=Decimal("0.1")) != a  # type: ignore[arg-type]
    assert compute_rule_signature(**base, decile_min_holdings=30) != a  # type: ignore[arg-type]
    assert compute_rule_signature(**base, min_price_floor=Decimal("10")) != a  # type: ignore[arg-type]
    assert compute_rule_signature(**base, min_adv_dollar=Decimal("2e6")) != a  # type: ignore[arg-type]
    assert compute_rule_signature(**base, adv_window_days=30) != a  # type: ignore[arg-type]


def test_canonical_gate_config_is_decile_frozen() -> None:
    # B1: 팩토리 기본값 = ADR-010 동결(decile·252/21·2000~2026·top_decile 전략). 단일 출처.
    cfg = canonical_gate_config()
    assert cfg.strategy_name == "top_decile_equal_weight"
    assert cfg.portfolio_pct == Decimal("0.10")
    assert cfg.decile_min_holdings == 20
    assert cfg.lookback_days == 252
    assert cfg.skip_recent_days == 21
    assert cfg.group_by_exchange is False
    assert cfg.start == date(2000, 1, 1)
    assert cfg.end == date(2026, 6, 18)


def test_decile_gate_signature_matches_ranking_signature() -> None:
    # B1 핵심: 게이트 decile config 의 rule_signature == ranking 요청(같은 momentum 파라미터)의
    # signature → flip 일관(정규값 발산=validated 영원히 false 함정 차단). R4 운영Top5↔decile 다리.
    gate_sig = _sig_from_config(canonical_gate_config())
    rank_sig = ranking_rule_signature(
        lookback_days=252, skip_recent_days=21, group_by_exchange=False
    )
    assert gate_sig == rank_sig


def test_ranking_signature_mismatch_on_wrong_lookback() -> None:
    # 검증된 룰(lookback 252)과 다른 lookback 요청은 signature 불일치 → flip false(검증 범위 밖).
    assert _sig_from_config(canonical_gate_config()) != ranking_rule_signature(
        lookback_days=126, skip_recent_days=21, group_by_exchange=False
    )


def test_r2_measurability_fails_on_excess_explosion() -> None:
    # ADR-010 #7 R2: |worst_oos_excess|>10 = 측정 artifact → r2 미통과·passed False
    # (G-3 는 전 fold>0 라 통과해도). 2차 폭발(e7)이 G-3 만으론 안 잡히는 갭을 R2 가 차단.
    kw = _pass_kwargs()
    kw["oos_excesses"] = (5.0, 1e7, 3.0)  # 전부 >0(G-3 통과) 이나 1e7 폭발
    r = evaluate_criteria(**kw)  # type: ignore[arg-type]
    assert r.g3_excess_pass is True
    assert r.r2_measurable is False
    assert r.passed is False


def test_r2_measurable_when_excess_bounded() -> None:
    # 정상 범위(|excess|<=10)면 측정 가능 → r2 통과(다른 G 통과 시 passed True).
    r = evaluate_criteria(**_pass_kwargs())  # type: ignore[arg-type]
    assert r.r2_measurable is True
    assert r.passed is True


# ── Task4: CLI 스모크(합성 데이터·전구간 8hr 전 배선 검증) ──


def test_main_cli_smoke_writes_result_and_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 합성 Parquet base_dir·--skip-verify·--n-folds 2 로 CLI 배선만 빠르게 확인(8hr 전 버그 차단).
    # 스냅샷 부재 → PriceDerivedUniverse(delisted_ratio=0 → G-5 fail) → passed=False 정상.
    base_dir = tmp_path / "parquet"
    base_dir.mkdir(parents=True)
    start = date(2025, 1, 1)
    bars = [
        DailyBar(
            ticker="NVDA",
            trade_date=start + timedelta(days=i),
            open=Decimal(100 + i),
            high=Decimal(105 + i),
            low=Decimal(95 + i),
            close=Decimal(100 + i),
            volume=1000,
            value=None,
            adj_factor=Decimal("1"),
        )
        for i in range(60)
    ]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=base_dir, source="synthetic")
    monkeypatch.setenv("STOCKPICK_DATA_DIR", str(base_dir))

    rc = s6_gate_main(["--skip-verify", "--n-folds", "2"])
    assert rc == 0
    result_file = base_dir / "s6_gate_result.json"
    assert result_file.is_file()  # 판정 영속
    import json as _json

    payload = _json.loads(result_file.read_text(encoding="utf-8"))
    assert payload["passed"] is False  # 합성·스냅샷부재·n_folds<10 → 미통과(정직)
    assert "rule_signature" in payload


def test_verify_gate_returns_report_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    # _verify_gate 가 verify_parquet.passed 를 그대로 전달(G-7 배선).
    class _Report:
        passed = True

    monkeypatch.setattr(storage, "verify_parquet", lambda base_dir: _Report())
    assert _verify_gate(Path("/x")) is True


def test_verify_gate_returns_false_on_verification_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # verify_parquet 가 VerificationError 던지면 False(데이터 신뢰 불가·게이트 fail 흡수).
    def _raise(base_dir: Path) -> object:
        raise storage.VerificationError("무결성 위반")

    monkeypatch.setattr(storage, "verify_parquet", _raise)
    assert _verify_gate(Path("/x")) is False


def test_walk_forward_yields_n_folds_when_data_sufficient() -> None:
    # 8hr 전 봉인: 데이터 충분 시 n_folds=10 분할이 정확히 10 fold 생성(세그먼트 off-by-one 차단).
    days = _weekdays(date(2018, 1, 1), 600)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"A": a})
    uni = FakeUniversePort(listed={"A": date(2017, 1, 1)}, delisted={})
    ident = StubIdentityResolver({"A": "C"})
    folds = walk_forward(
        _cfg(days, lookback_days=5),
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=_NOLIQ,
        n_folds=10,
        purge_gap_days=5,
    )
    assert len(folds) == 10  # G-4(n_folds>=10) 가 풀데이터서 충족됨을 봉인


def test_main_cli_master_universe_threads_delisted_ratio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 실제 실행 경로 봉인: stock_snapshot.json 존재 → MasterUniverse → delisted_ratio 결과에 전달.
    base_dir = tmp_path / "parquet"
    base_dir.mkdir(parents=True)
    start = date(2025, 1, 1)
    bars = [
        DailyBar(
            ticker="NVDA",
            trade_date=start + timedelta(days=i),
            open=Decimal(100 + i),
            high=Decimal(105 + i),
            low=Decimal(95 + i),
            close=Decimal(100 + i),
            volume=1000,
            value=None,
            adj_factor=Decimal("1"),
        )
        for i in range(60)
    ]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=base_dir, source="synthetic")
    # 2종목 중 1종목 폐지 → delisted_ratio=0.5(MasterUniverse 멤버십 기준).
    import json as _json

    (base_dir / "stock_snapshot.json").write_text(
        _json.dumps(
            {
                "stocks": [
                    {"ticker": "NVDA", "listed_at": "2025-01-01", "delisted_at": None},
                    {"ticker": "DEAD", "listed_at": "2025-01-01", "delisted_at": "2025-02-01"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("STOCKPICK_DATA_DIR", str(base_dir))

    rc = s6_gate_main(["--skip-verify", "--n-folds", "2"])
    assert rc == 0
    payload = _json.loads((base_dir / "s6_gate_result.json").read_text(encoding="utf-8"))
    assert payload["delisted_ratio"] == 0.5  # MasterUniverse 폐지비율 전달 확인


def test_run_s6_gate_short_circuits_when_verify_failed() -> None:
    # G-7(verify) 실패 → 백테스트 미실행 단락(garbage-in 방지·OOM/8hr 회피). passed=false·g7=false.
    port, uni, ident = _ports()
    days = port.trading_days()
    cfg = _cfg(days)
    r = run_s6_gate(
        cfg,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=_NOLIQ,
        delisted_ratio=0.5,
        verify_passed=False,  # 무결성 실패 주입
        n_folds=2,
        purge_gap_days=5,
    )
    assert r.passed is False
    assert r.g7_verify_pass is False
    assert r.n_folds == 0  # 백테스트 미실행(단락)
    assert r.sensitivity == {}
    assert r.rule_signature  # signature 는 기록(데이터 무관)
    assert any("백테스트 미실행" in n for n in r.notes)


def test_run_s6_gate_does_not_call_backtest_when_verify_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 단락 비용-회피 계약 직접 봉인: verify_passed=False 면 walk_forward_by_cost 가 호출되면 안 됨.
    import stockpick.backtest.s6_gate as s6mod

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("백테스트(walk_forward_by_cost) 호출됨 — 단락 실패")

    monkeypatch.setattr(s6mod, "walk_forward_by_cost", _boom)
    port, uni, ident = _ports()
    days = port.trading_days()
    r = run_s6_gate(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=_NOLIQ,
        delisted_ratio=0.5,
        verify_passed=False,
        n_folds=2,
    )
    assert r.passed is False  # _boom 미발생 = 백테스트 미호출(단락 작동)


def test_rule_signature_includes_period_return_cap() -> None:
    # A1p2 L4: cap 은 수익 계산식을 바꾸므로 rule_signature 에 포함 — 비정규 cap 게이트는 flip 불가.
    base = dict(
        strategy_name="equal_weight_top_n",
        top_n=5,
        lookback_days=126,
        skip_recent_days=21,
        rebalance_freq="monthly",
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
    )
    sig_default = compute_rule_signature(**base)  # type: ignore[arg-type]
    sig_canon = compute_rule_signature(**base, period_return_cap=Decimal("1.0"))  # type: ignore[arg-type]  # ADR-010 ±100% clip
    sig_other = compute_rule_signature(**base, period_return_cap=Decimal("5.0"))  # type: ignore[arg-type]
    assert sig_default == sig_canon  # 기본값=정규 동결값(ADR-010 cap=1.0·인자 생략=정규 매칭)
    assert sig_canon != sig_other  # 비정규 cap → 다른 룰 정체성


# ── Phase 2-9: decile 게이트 wiring smoke(canonical 경로 8hr 전 배선 봉인) ──


def test_decile_gate_wiring_smoke() -> None:
    # B1/배선 봉인: decile config(portfolio_pct)+TopDecileEqualWeight+liquidity 로 run_s6_gate 가
    # 끝까지 돌고 fold 생성·rule_signature 가 config 신필드(decile/유동성)와 일치. canonical 경로와
    # 동일 코드(축소 lookback)라 8hr 전 wiring 버그(빈 fold·signature 발산)를 분 단위로 차단.
    days = _weekdays(date(2018, 1, 1), 400)
    n = 30
    series = {
        f"T{i:02d}": [PricePoint(d, Decimal(100 + i + j)) for j, d in enumerate(days)]
        for i in range(n)
    }
    port = FakePriceSeriesPort(series)
    uni = FakeUniversePort(listed={tk: date(2017, 1, 1) for tk in series}, delisted={})
    ident = StubIdentityResolver({})
    cfg = _cfg(
        days,
        strategy_name="top_decile_equal_weight",
        lookback_days=10,
        skip_recent_days=2,
        cost_bps=Decimal("10"),
        portfolio_pct=Decimal("0.1"),
        decile_min_holdings=5,
    )
    strat = TopDecileEqualWeight(pct=Decimal("0.1"), min_holdings=5)
    r = run_s6_gate(
        cfg,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=strat,
        liquidity_port=_NOLIQ,
        delisted_ratio=0.5,
        verify_passed=True,
        n_folds=2,
        purge_gap_days=12,
    )
    assert isinstance(r, S6GateResult)
    assert r.n_folds > 0  # decile 경로가 실제 fold 생성(빈 폴드면 배선 미작동)
    # signature 가 decile/유동성 신필드 반영(compute_rule_signature 동일 구성).
    assert r.rule_signature == compute_rule_signature(
        strategy_name=cfg.strategy_name,
        top_n=cfg.top_n,
        lookback_days=cfg.lookback_days,
        skip_recent_days=cfg.skip_recent_days,
        rebalance_freq=cfg.rebalance_freq,
        delisting_recovery_rate=cfg.delisting_recovery_rate,
        group_by_exchange=cfg.group_by_exchange,
        period_return_cap=cfg.period_return_cap,
        portfolio_pct=cfg.portfolio_pct,
        decile_min_holdings=cfg.decile_min_holdings,
        min_price_floor=cfg.min_price_floor,
        min_adv_dollar=cfg.min_adv_dollar,
        adv_window_days=cfg.adv_window_days,
    )
