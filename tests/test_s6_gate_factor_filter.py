"""B P3 — s6_gate factor_filter(H1)·G-5c 관측(H9)·archive(H10) — 합성·라이브 0.

핵심 회귀: **off(apply_roe_filter=False)=momentum canonical signature bit-identical**·on≠off·
G-5c 는 passed AND 밖(관측)·archive 는 이전 판정 삭제 대신 JSONL 보존(다중검정).
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.fakes import (
    FakeLiquidityPort,
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.s6_gate import (
    S6GateResult,
    _archive_stale_result,
    canonical_gate_config,
    compute_rule_signature,
    evaluate_criteria,
    ranking_rule_signature,
    run_s6_gate,
    write_s6_gate_result,
)
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.rules._scan import PricePoint
from stockpick.types import FinancialFact

_RESULT_NAME = "s6_gate_result.json"


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _sig_base() -> dict[str, object]:
    return dict(
        strategy_name="top_decile_equal_weight",
        top_n=5,
        lookback_days=252,
        skip_recent_days=21,
        rebalance_freq="monthly",
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
    )


# ── H1: factor_filter off=bit-identical / on≠off ────────────────────────────


def test_signature_factor_filter_off_bit_identical() -> None:
    base = _sig_base()
    momentum = compute_rule_signature(**base)  # type: ignore[arg-type]
    # off(명시) — 기본 파라미터 넘겨도 factor_filter 키 미삽입 → payload 바이트 동일 → 해시 동일.
    off = compute_rule_signature(
        **base,  # type: ignore[arg-type]
        apply_roe_filter=False,
        min_roe=Decimal("0.5"),  # off 면 무시돼야(키 미삽입)
        roe_max_age_days=548,
    )
    assert off == momentum  # 최우선: off=momentum canonical bit-identical


def test_signature_factor_filter_on_differs() -> None:
    base = _sig_base()
    momentum = compute_rule_signature(**base)  # type: ignore[arg-type]
    on = compute_rule_signature(
        **base,  # type: ignore[arg-type]
        apply_roe_filter=True,
        min_roe=Decimal("0"),
        roe_max_age_days=548,
    )
    assert on != momentum  # 하드필터 룰 = 다른 정체성(검증범위 오클레임 차단)
    # roe_max_age 나 min_roe 가 다르면 또 다른 해시(동결 우회 차단).
    on2 = compute_rule_signature(
        **base,  # type: ignore[arg-type]
        apply_roe_filter=True,
        min_roe=Decimal("0"),
        roe_max_age_days=365,
    )
    assert on2 != on
    on3 = compute_rule_signature(
        **base,  # type: ignore[arg-type]
        apply_roe_filter=True,
        min_roe=Decimal("0.1"),
        roe_max_age_days=548,
    )
    assert on3 != on


def test_ranking_and_canonical_signature_off_match_momentum() -> None:
    # 3자 off 일관: ranking_rule_signature(off) == canonical_gate_config(off) 유래 signature.
    cfg = canonical_gate_config()  # off(momentum) 기본
    from_cfg = compute_rule_signature(
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
        apply_roe_filter=cfg.apply_roe_filter,
        min_roe=cfg.min_roe,
        roe_max_age_days=cfg.roe_max_age_days,
    )
    from_route = ranking_rule_signature(
        lookback_days=252, skip_recent_days=21, group_by_exchange=False
    )
    assert from_cfg == from_route  # 게이트·route 가 같은 momentum 룰 → 같은 키(flip 일관)


def test_ranking_signature_on_differs_from_off() -> None:
    off = ranking_rule_signature(lookback_days=252, skip_recent_days=21, group_by_exchange=False)
    on = ranking_rule_signature(
        lookback_days=252, skip_recent_days=21, group_by_exchange=False,
        apply_roe_filter=True, min_roe=Decimal("0"), roe_max_age_days=548,
    )
    assert on != off  # route 가 B 룰 요청 시 momentum 판정과 매칭 안 됨(보수)


# ── H9: G-5c 관측 필드는 passed AND 밖 ──────────────────────────────────────


def _passing_result() -> S6GateResult:
    return evaluate_criteria(
        rule_signature="SIG",
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


def test_g5c_defaults_empty_and_not_in_passed() -> None:
    r = _passing_result()
    assert r.passed is True
    # evaluate_criteria 는 G-5c 안 채움(관측·run_s6_gate 가 attach)
    assert r.g5c_coverage_rates == ()
    assert r.g5c_survivor_counts == ()
    assert r.g5c_mnar_skew is None
    # 최악의 G-5c(커버 0·생존 0)를 붙여도 passed 불변 — validated 는 G-1~G-8·R-2 뿐(H9).
    bad = replace(
        r, g5c_coverage_rates=(0.0,) * 10, g5c_survivor_counts=(0,) * 10, g5c_mnar_skew=9.9
    )
    assert bad.passed is True


# ── H10: archive 다중검정 보존 ──────────────────────────────────────────────


def test_archive_stale_result_appends_jsonl(tmp_path: Path) -> None:
    write_s6_gate_result(tmp_path, replace(_passing_result(), rule_signature="SIG1"))
    path = tmp_path / _RESULT_NAME
    _archive_stale_result(path)
    write_s6_gate_result(tmp_path, replace(_passing_result(), rule_signature="SIG2"))
    _archive_stale_result(path)
    archive = tmp_path / (_RESULT_NAME + ".archive")
    lines = [ln for ln in archive.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2  # 두 시도 이력 보존(덮어쓰기 아님)
    sigs = [json.loads(ln)["rule_signature"] for ln in lines]
    assert sigs == ["SIG1", "SIG2"]


def test_archive_corrupt_file_preserved_raw(tmp_path: Path) -> None:
    path = tmp_path / _RESULT_NAME
    path.write_text("{not json", encoding="utf-8")
    _archive_stale_result(path)  # 파싱 실패해도 유실 금지
    archive = tmp_path / (_RESULT_NAME + ".archive")
    line = archive.read_text(encoding="utf-8").strip()
    assert json.loads(line)["raw"] == "{not json"  # 원문 래핑 보존


# ── run_s6_gate 통합: off=g5c 빈값 / on=g5c 채움·signature 다름 ──────────────


def _fin_facts() -> list[FinancialFact]:
    def f(cik: str, concept: str, value: str) -> FinancialFact:
        return FinancialFact(
            cik=cik,
            concept=concept,
            fiscal_period="2022-FY",
            period_end=date(2022, 12, 31),
            disclosed_at=date(2023, 3, 1),
            value=Decimal(value),
        )

    return [
        f("CIK_A", "StockholdersEquity", "1000"),
        f("CIK_A", "NetIncomeLoss", "200"),  # ROE 0.2 흑자
        f("CIK_B", "StockholdersEquity", "1000"),
        f("CIK_B", "NetIncomeLoss", "-50"),  # 적자
    ]


def _gate_ports() -> tuple[FakePriceSeriesPort, FakeUniversePort, StubIdentityResolver]:
    days = _weekdays(date(2024, 1, 1), 250)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]  # 상승(흑자)
    b = [PricePoint(d, Decimal(100 + 2 * i)) for i, d in enumerate(days)]  # 더 급상승(적자)
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(
        listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={}
    )
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    return port, uni, ident


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


def test_run_s6_gate_off_no_g5c_measured() -> None:
    # momentum(off): G-5c 관측 미측정(빈값 유지) — 재무 팩터 무관 게이트.
    port, uni, ident = _gate_ports()
    days = port.trading_days()
    r = run_s6_gate(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
        delisted_ratio=0.5,
        verify_passed=True,
        n_folds=2,
        purge_gap_days=5,
    )
    assert r.g5c_coverage_rates == ()
    assert r.g5c_survivor_counts == ()


def test_run_s6_gate_on_measures_g5c_and_signature_includes_filter() -> None:
    # apply_roe_filter=True: G-5c fold별 관측 채워짐 + rule_signature 에 factor_filter 반영.
    port, uni, ident = _gate_ports()
    days = port.trading_days()
    cfg_on = _cfg(days, apply_roe_filter=True, min_roe=Decimal("0"))
    r = run_s6_gate(
        cfg_on,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
        delisted_ratio=0.5,
        verify_passed=True,
        financial_facts=_fin_facts(),
        n_folds=2,
        purge_gap_days=5,
    )
    assert len(r.g5c_coverage_rates) == r.n_folds  # fold별 커버율
    assert len(r.g5c_survivor_counts) == r.n_folds
    assert all(c >= 1 for c in r.g5c_survivor_counts)  # A(흑자) 매 fold 생존
    # signature 는 momentum-only 와 다름(factor_filter 포함).
    momentum_sig = run_s6_gate(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
        delisted_ratio=0.5,
        verify_passed=True,
        n_folds=2,
        purge_gap_days=5,
    ).rule_signature
    assert r.rule_signature != momentum_sig
