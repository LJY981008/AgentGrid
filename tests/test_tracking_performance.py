"""M4 P5 — 성과 계산(tracking/performance) TDD. 합성·라이브 0.

핵심 검증: 분할 정규화 연속성·활성-only 공통 as-of·**중간 현금흐름에서 TWR 오염 0**
(단순수익률 붕괴 케이스)·모델 계열 앵커 고정가중 드리프트·폐지 동결·MDD·기여도·슬리피지.
전 계열 price return(배당 미반영·스펙 §3.1) — raw close + SPLIT 정규화만.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from stockpick.tracking.ledger import replay_ledger
from stockpick.tracking.performance import (
    actual_series,
    model_series,
    normalize_splits,
    resolve_as_of,
)
from stockpick.tracking.types import CashFlow, PortfolioRound, SplitEvent, Trade, TradeSide

_STAMP = datetime(2026, 7, 2, tzinfo=UTC)
_D = [date(2026, 7, d) for d in range(1, 8)]  # D[0]=7/1 .. D[6]=7/7


def _split(ticker: str, day: date, ratio: str) -> SplitEvent:
    return SplitEvent(
        ticker=ticker, effective_on=day, ratio=Decimal(ratio), source="test", ingested_at=_STAMP
    )


def _closes(*pairs: tuple[date, str]) -> list[tuple[date, Decimal]]:
    return [(d, Decimal(c)) for d, c in pairs]


# ── normalize_splits ────────────────────────────────────────────────────────


def test_normalize_splits_makes_series_continuous() -> None:
    # 2:1 분할(D2 효력·당일 가격 이미 반영): raw 100 → 50. 정규화 N_t = raw×Π(ratio≤t) 로 연속.
    raw = _closes((_D[0], "100"), (_D[1], "50"), (_D[2], "51"))
    out = normalize_splits(raw, [_split("AAA", _D[1], "2")])
    assert out == _closes((_D[0], "100"), (_D[1], "100"), (_D[2], "102"))


def test_normalize_splits_no_events_identity() -> None:
    raw = _closes((_D[0], "100"), (_D[1], "101"))
    assert normalize_splits(raw, []) == raw


# ── resolve_as_of ───────────────────────────────────────────────────────────


def test_resolve_as_of_min_of_active_only() -> None:
    max_dates = {"AAA": _D[4], "BBB": _D[2], "DEAD": _D[0]}
    # 폐지(DEAD)는 제외 — 포함하면 전체가 D0 로 절단(폐지 청산 규약과 충돌·C-3).
    as_of = resolve_as_of(max_dates, required={"AAA", "BBB", "DEAD"}, inactive={"DEAD"})
    assert as_of == _D[2]


def test_resolve_as_of_all_inactive_none() -> None:
    assert resolve_as_of({}, required={"AAA"}, inactive=set()) is None  # 무데이터=측정불가


# ── actual_series(TWR) ──────────────────────────────────────────────────────


def test_actual_twr_immune_to_mid_flow() -> None:
    # 단순수익률 붕괴 케이스(GIPS blocking): D1 $1000 입금·10주 BUY@100 → D2 +10%(110)
    # → D3 $1100 추가입금 → D4 시장 변동 0. TWR = +10% 정확(추가입금 오염 0).
    trades = [
        Trade(
            id=1, round_id=1, stock_id=1, ticker="AAA", side=TradeSide.BUY,
            quantity=Decimal("10"), price=Decimal("100"), fee=Decimal("0"), executed_on=_D[0],
        )
    ]
    flows = [
        CashFlow(id=1, round_id=1, amount=Decimal("1000"), flowed_on=_D[0]),
        CashFlow(id=2, round_id=1, amount=Decimal("1100"), flowed_on=_D[2]),
    ]
    grid = [_D[0], _D[1], _D[2], _D[3]]
    ledger = replay_ledger(trades, flows, {}, grid)
    closes = {
        "AAA": {
            _D[0]: Decimal("100"),
            _D[1]: Decimal("110"),
            _D[2]: Decimal("110"),
            _D[3]: Decimal("110"),
        }
    }
    perf = actual_series(ledger, closes, liquidations={})
    assert perf.cumulative_return == pytest.approx(Decimal("0.1"))  # 정확히 +10%
    assert perf.index[-1][1] == pytest.approx(Decimal("1.1"))


def test_actual_twr_missing_close_carries_forward() -> None:
    trades = [
        Trade(
            id=1, round_id=1, stock_id=1, ticker="AAA", side=TradeSide.BUY,
            quantity=Decimal("10"), price=Decimal("100"), fee=Decimal("0"), executed_on=_D[0],
        )
    ]
    flows = [CashFlow(id=1, round_id=1, amount=Decimal("1000"), flowed_on=_D[0])]
    grid = [_D[0], _D[1], _D[2]]
    ledger = replay_ledger(trades, flows, {}, grid)
    closes = {"AAA": {_D[0]: Decimal("100"), _D[2]: Decimal("120")}}  # D1 결측(정지)
    perf = actual_series(ledger, closes, liquidations={})
    # D1 은 직전가 100 carry-forward(변동 0), D2 +20%.
    assert perf.index[1][1] == pytest.approx(Decimal("1"))
    assert perf.cumulative_return == pytest.approx(Decimal("0.2"))


def test_actual_series_mdd() -> None:
    trades = [
        Trade(
            id=1, round_id=1, stock_id=1, ticker="AAA", side=TradeSide.BUY,
            quantity=Decimal("10"), price=Decimal("100"), fee=Decimal("0"), executed_on=_D[0],
        )
    ]
    flows = [CashFlow(id=1, round_id=1, amount=Decimal("1000"), flowed_on=_D[0])]
    grid = [_D[0], _D[1], _D[2]]
    ledger = replay_ledger(trades, flows, {}, grid)
    closes = {
        "AAA": {_D[0]: Decimal("100"), _D[1]: Decimal("80"), _D[2]: Decimal("90")}
    }
    perf = actual_series(ledger, closes, liquidations={})
    assert perf.max_drawdown == pytest.approx(0.2)  # 100→80 = −20% 낙폭(float 격리)


# ── model_series(등가중 앵커 고정가중·드리프트·폐지 동결) ────────────────────


def test_model_series_equal_weight_drift() -> None:
    grid = [_D[0], _D[1]]
    closes_norm = {
        "AAA": {_D[0]: Decimal("100"), _D[1]: Decimal("110")},  # +10%
        "BBB": {_D[0]: Decimal("50"), _D[1]: Decimal("45")},  # −10%
    }
    perf = model_series(["AAA", "BBB"], anchor=_D[0], closes_norm=closes_norm, grid=grid, frozen={})
    assert perf.cumulative_return == pytest.approx(Decimal("0"))  # 등가중 평균 0%
    assert perf.index[-1][1] == pytest.approx(Decimal("1"))


def test_model_series_frozen_liquidation_no_redistribution() -> None:
    # BBB 가 D1 이후 폐지(frozen=D1·마지막 유효가) — 이후 BBB 지수 동결(재분배 금지)·AAA 만 움직임.
    grid = [_D[0], _D[1], _D[2]]
    closes_norm = {
        "AAA": {_D[0]: Decimal("100"), _D[1]: Decimal("100"), _D[2]: Decimal("120")},
        "BBB": {_D[0]: Decimal("50"), _D[1]: Decimal("40")},  # D2 없음(폐지)
    }
    perf = model_series(
        ["AAA", "BBB"], anchor=_D[0], closes_norm=closes_norm, grid=grid, frozen={"BBB": _D[1]}
    )
    # D2: AAA G=1.2·BBB G=0.8(동결) → index=(1.2+0.8)/2=1.0
    assert perf.index[-1][1] == pytest.approx(Decimal("1"))


def test_model_series_unmeasurable_ticker_excluded_and_reported() -> None:
    grid = [_D[0], _D[1]]
    closes_norm = {"AAA": {_D[0]: Decimal("100"), _D[1]: Decimal("110")}}
    perf = model_series(
        ["AAA", "GHOST"], anchor=_D[0], closes_norm=closes_norm, grid=grid, frozen={}
    )
    # GHOST 앵커가 없음 → 배제 + unmeasurable 보고(조용한 누락 금지) → AAA 단독 +10%.
    assert perf.cumulative_return == pytest.approx(Decimal("0.1"))
    assert perf.unmeasurable == ("GHOST",)


# ── compute_round_performance(통합) ─────────────────────────────────────────


def _mk_round() -> PortfolioRound:
    from stockpick.tracking.types import RoundStatus, SnapshotEntry

    def entry(t: str, rank: int) -> SnapshotEntry:
        return SnapshotEntry(
            cik=f"{rank:010d}", ticker=t, exchange="NASDAQ", rank=rank, score=1.0 - rank / 10,
            factors={}, anchor_close=None,
        )

    return PortfolioRound(
        id=1, label="2026-07", status=RoundStatus.OPEN, opened_on=_D[0], anchor_as_of=_D[0],
        top20_snapshot=(entry("AAA", 1), entry("BBB", 2)), rule_signature="SIG",
        validated=False, top5=("AAA",),
    )


def test_compute_round_performance_integration() -> None:
    from stockpick.tracking.performance import compute_round_performance

    rnd = _mk_round()
    trades = [
        Trade(
            id=1, round_id=1, stock_id=1, ticker="AAA", side=TradeSide.BUY,
            quantity=Decimal("10"), price=Decimal("101"), fee=Decimal("0"), executed_on=_D[0],
        )
    ]
    flows = [CashFlow(id=1, round_id=1, amount=Decimal("1010"), flowed_on=_D[0])]
    closes = {
        "AAA": _closes((_D[0], "100"), (_D[1], "110"), (_D[2], "120")),  # +20%
        "BBB": _closes((_D[0], "50"), (_D[1], "50"), (_D[2], "50")),  # 0%
    }
    spy_closes = _closes((_D[0], "500"), (_D[1], "505"), (_D[2], "510"))  # +2%
    perf = compute_round_performance(
        rnd,
        trades=trades,
        flows=flows,
        splits={},
        closes=closes,
        spy_closes=spy_closes,
        spy_splits=[],
        delisted=set(),
        today=_D[3],
        n_picks_prior=0,
    )
    assert perf.as_of == _D[2]  # 공통 as-of = 전 활성 min(max date)
    assert perf.grid[0] == _D[0] and perf.grid[-1] == _D[2]  # SPY 거래일 그리드
    # 계열: top5(AAA)=+20% · top20 등가중=(20%+0%)/2=+10% · SPY=+2%.
    assert perf.top5_model.cumulative_return == pytest.approx(Decimal("0.2"))
    assert perf.top20_model.cumulative_return == pytest.approx(Decimal("0.1"))
    assert perf.spy.cumulative_return == pytest.approx(Decimal("0.02"))
    # 실보유: 체결 101(종가 100 대비 슬리피지 1%) → 평가 100→120 이나 진입 101 반영 TWR.
    assert perf.actual.cumulative_return > Decimal("0.15")
    # 파생: 선택효과=+10%p·실행효과=실보유−top5(체결가·현금드래그).
    assert perf.selection_effect == pytest.approx(0.1)
    assert perf.execution_effect == pytest.approx(
        float(perf.actual.cumulative_return - perf.top5_model.cumulative_return)
    )
    # 기여도: AAA pnl = 10×120 − (10×101) = +190.
    contrib = {c.ticker: c for c in perf.contributions}
    assert contrib["AAA"].pnl == Decimal("190")
    # 슬리피지: BUY 101 vs 당일종가 100 → +1%(불리).
    assert perf.slippages[0].cost_pct == pytest.approx(0.01)
    # 히트레이트: AAA 모델수익 +20%>0 → 1/1. 판정유보: 누적 1<20.
    assert perf.hit_rate == pytest.approx(1.0)
    assert perf.verdict_deferred is True
    assert perf.stale is False  # today=as_of+1일


def test_compute_round_performance_stale_flag() -> None:
    from stockpick.tracking.performance import compute_round_performance

    rnd = _mk_round()
    closes = {
        "AAA": _closes((_D[0], "100")),
        "BBB": _closes((_D[0], "50")),
    }
    perf = compute_round_performance(
        rnd, trades=[], flows=[], splits={}, closes=closes,
        spy_closes=_closes((_D[0], "500")), spy_splits=[], delisted=set(),
        today=date(2026, 7, 20), n_picks_prior=0,  # as_of=7/1 → 19일 경과
    )
    assert perf.stale is True
