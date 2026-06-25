"""엔진 테스트 — 결정적 합성 가격(라이브 0). 룩어헤드(진입 t+1)·폐지청산 검증."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import _holding_period_return, _rank_at, run
from stockpick.backtest.fakes import (
    FakeLiquidityPort,
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
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


def test_rising_winner_grows_equity_no_delisting() -> None:
    # A 단조 상승, B 평탄 → top_n=1 은 매 리밸 A 선택 → equity 상승. 폐지 0.
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal("100")) for d in days]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    res = run(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"}),
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
    )
    assert res.total_return > Decimal("0")
    assert res.n_delisted_liquidations == 0
    assert res.n_rebalances >= 1


def test_delisting_during_holding_realizes_total_loss() -> None:
    # A 보유 중 폐지(recovery_rate=0) → 그 구간 -100% → n_delisted>=1, 손실 반영.
    days = _weekdays(date(2024, 1, 1), 70)
    de = date(2024, 2, 15)  # 목요일 — days 에 포함
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days) if d < de]
    b = [PricePoint(d, Decimal("100")) for d in days]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(
        listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={"A": de}
    )
    res = run(
        _cfg(days, delisting_recovery_rate=Decimal("0")),
        price_port=port,
        universe_port=uni,
        identity=StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"}),
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
    )
    assert res.n_delisted_liquidations >= 1
    # 금액 봉인: recovery_rate=0 → A(상승추세라 매 리밸 선택) 보유 중 폐지 = 그 기간 -100%
    # → 전액 손실. 이후 B(평탄)도 0 수익이라 최종 equity 0, total_return 정확히 -1.
    assert res.total_return == Decimal("-1")


def test_empty_universe_flat_equity() -> None:
    # 거래가능 종목 0 → 랭킹 빈 → 수익 0 → total_return 0.
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"A": a})
    uni = FakeUniversePort(listed={"A": date(2099, 1, 1)}, delisted={})  # 미래상장 → 항상 제외
    res = run(
        _cfg(days),
        price_port=port,
        universe_port=uni,
        identity=StubIdentityResolver({"A": "CIK_A"}),
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
    )
    assert res.total_return == Decimal("0")


# --- 수익률 처리: per-ticker simple return clip(ADR-010 ±100%·증폭기 root fix) ---


def _hold1(
    pts: list[PricePoint], *, recovery: str = "0", de: date | None = None, cap: str = "1.0"
) -> Decimal:
    entry, exit_ = pts[0].trade_date, pts[-1].trade_date
    delisted: dict[str, date | None] = {} if de is None else {"A": de}
    uni = FakeUniversePort(listed={"A": date(2000, 1, 1)}, delisted=delisted)
    total, _d, _s = _holding_period_return(
        {"A": Decimal("1")},
        {"A": "A"},
        {"A": pts},
        entry,
        exit_,
        uni,
        Decimal(recovery),
        Decimal(cap),
    )
    return total


def _pp(d: tuple[int, int, int], price: str) -> PricePoint:
    return PricePoint(date(*d), Decimal(price))


def test_holding_return_caps_upper_explosion() -> None:
    # 극소 진입가/잔존 garbage → 199999배 → +100% clip(ADR-010·증폭기 차단).
    assert _hold1([_pp((2024, 1, 2), "5"), _pp((2024, 1, 31), "1000000")]) == Decimal("1.0")


def test_holding_return_no_floor_preserves_real_loss() -> None:
    # ⚠️ 하한 floor 없음 — 정상 종목 실손실(-99.9995%)을 마스킹하지 않음(정직). ret>=-1 보장.
    expected = Decimal("5") / Decimal("1000000") - Decimal("1")
    assert _hold1([_pp((2024, 1, 2), "1000000"), _pp((2024, 1, 31), "5")]) == expected


def test_holding_return_clips_legit_large_gain() -> None:
    # ADR-010: 실재 대급등(GME 16.2x·ret 15.2)도 +100% clip — +1900%/월급 cap-hit 은 정상 알파
    # 아님(0a 증폭기 확정). A1p2 의 GME 보존(+19)은 Phase 0a 진단서 폐기(증폭기 root).
    assert _hold1([_pp((2024, 1, 2), "10"), _pp((2024, 1, 31), "162")]) == Decimal("1.0")


def test_holding_return_below_clip_unchanged() -> None:
    # clip 안쪽 정상 수익(+50%)은 무변경(기계 검증).
    assert _hold1([_pp((2024, 1, 2), "100"), _pp((2024, 1, 31), "150")]) == Decimal("0.5")


def test_holding_return_delisting_recovery0_stays_total_loss() -> None:
    # ⚠️ 폐지 청산(recovery=0)은 -100% 가 정답(상한캡은 손실에 무영향).
    # de(01-16) ∈ (entry 01-02, exit 01-31] → 폐지경로. last_p=de 직전(01-15=90).
    de = date(2024, 1, 16)
    pts = [_pp((2024, 1, 2), "100"), _pp((2024, 1, 15), "90"), _pp((2024, 1, 31), "50")]
    assert _hold1(pts, recovery="0", de=de) == Decimal("-1")


def test_period_return_cap_in_fingerprint() -> None:
    # cap 은 재현성 입력 — fingerprint 에 반영(다르면 다른 해시).
    days = _weekdays(date(2024, 1, 1), 10)
    assert (
        _cfg(days, period_return_cap=Decimal("19.0")).fingerprint()
        != _cfg(days, period_return_cap=Decimal("5.0")).fingerprint()
    )


def test_period_return_cap_must_be_positive() -> None:
    # cap<=0 은 모든 수익을 음수로 뭉갬 → 명시 실패(조용한 오설정 금지).
    days = _weekdays(date(2024, 1, 1), 10)
    with pytest.raises(ValueError, match="period_return_cap"):
        _cfg(days, period_return_cap=Decimal("0"))


def test_liquidity_fields_in_fingerprint() -> None:
    # ADR-010 유동성 임계는 유니버스를 바꿈 → 재현성 fingerprint 반영(다르면 다른 해시).
    days = _weekdays(date(2024, 1, 1), 10)
    base = _cfg(days).fingerprint()
    assert _cfg(days, min_price_floor=Decimal("10")).fingerprint() != base
    assert _cfg(days, min_adv_dollar=Decimal("2000000")).fingerprint() != base
    assert _cfg(days, adv_window_days=30).fingerprint() != base


def test_liquidity_fields_must_be_positive() -> None:
    days = _weekdays(date(2024, 1, 1), 10)
    for field, val in (
        ("min_price_floor", Decimal("0")),
        ("min_adv_dollar", Decimal("0")),
        ("adv_window_days", 0),
    ):
        with pytest.raises(ValueError, match=field):
            _cfg(days, **{field: val})


# --- 유동성 PIT 필터 배선(ADR-010·engine·룩어헤드 ≤t·생존편향 대칭) ---


def test_rank_at_applies_liquidity_filter() -> None:
    # 후보 A,B 둘 다 모멘텀 산출되지만 유동성 포트가 {"A"}만 통과 → 랭킹에서 B 제외(필터 발동).
    days = _weekdays(date(2024, 1, 1), 40)
    t = days[20]
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal(100 + 3 * i)) for i, d in enumerate(days)]  # 모멘텀 더 강함
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    ident = StubIdentityResolver({})
    cfg = _cfg(days, top_n=2)
    exch = port.ticker_exchanges()
    ranked_all = _rank_at(cfg, port, uni, ident, exch, t, FakeLiquidityPort(None))
    ranked_liq = _rank_at(cfg, port, uni, ident, exch, t, FakeLiquidityPort({"A"}))
    assert {e.ticker for e in ranked_all} == {"A", "B"}  # 필터 off → 둘 다
    assert {e.ticker for e in ranked_liq} == {"A"}  # 필터 on → B(비유동) 제외


def test_rank_at_decile_mode_returns_full_candidate_pool() -> None:
    # decile 모드(portfolio_pct 설정): _rank_at 가 top_n 으로 자르지 않고 전 후보 반환(전략이
    # decile 선택). 고정 모드(portfolio_pct None)는 top_n 절단. M1 분모 = 후보 수.
    days = _weekdays(date(2024, 1, 1), 40)
    t = days[20]
    n = 30
    series = {
        f"T{i:02d}": [PricePoint(d, Decimal(100 + i + j)) for j, d in enumerate(days)]
        for i in range(n)
    }
    port = FakePriceSeriesPort(series)
    uni = FakeUniversePort(listed={tk: date(2023, 1, 1) for tk in series}, delisted={})
    ident = StubIdentityResolver({})
    exch = port.ticker_exchanges()
    nofilter = FakeLiquidityPort(None)
    ranked_decile = _rank_at(
        _cfg(days, top_n=5, portfolio_pct=Decimal("0.1")), port, uni, ident, exch, t, nofilter
    )
    ranked_fixed = _rank_at(_cfg(days, top_n=5), port, uni, ident, exch, t, nofilter)
    assert len(ranked_decile) == n  # 전 후보(자르지 않음 → 전략이 decile)
    assert len(ranked_fixed) == 5  # top_n 절단(고정 모드)


def test_liquidity_filter_changes_holdings_end_to_end() -> None:
    # run() 전 구간: B 모멘텀 최고지만 유동성 {"A"}만 통과 → A 보유. 필터 off 와 결과 달라짐.
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal(100 + 3 * i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={})
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    cfg = _cfg(days, top_n=1)
    r_all = run(
        cfg,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort(None),
    )
    r_liq = run(
        cfg,
        price_port=port,
        universe_port=uni,
        identity=ident,
        strategy=EqualWeightTopN(),
        liquidity_port=FakeLiquidityPort({"A"}),
    )
    assert r_all.total_return != r_liq.total_return  # 필터가 선택 종목을 바꿈
