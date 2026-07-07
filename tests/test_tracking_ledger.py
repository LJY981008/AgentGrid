"""M4 P4 — 전역 포지션 원장(tracking/ledger) TDD. 합성·라이브 0.

일중 순서 규약 동결: **SPLIT(장 시작·수량×ratio) → 외부 현금흐름 → trade(id 오름차순) →
평가(종가·performance 층)**. 불변식: positions≥0·cash≥0(위반=LedgerError 명시 실패).
분할 수량 보정은 SPLIT 이벤트만(adj_factor 오용 금지 — acceptance: effective_on=분할 후
첫 거래일이라 effective_on 당일 장 시작에 적용).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from stockpick.tracking.ledger import (
    LedgerError,
    replay_ledger,
    validate_new_trade,
    validate_void,
)
from stockpick.tracking.types import CashFlow, SplitEvent, Trade, TradeSide

_STAMP = datetime(2026, 7, 2, tzinfo=UTC)


def _trade(
    tid: int | None,
    ticker: str,
    side: TradeSide,
    qty: str,
    price: str,
    day: date,
    *,
    fee: str = "0",
) -> Trade:
    return Trade(
        id=tid,
        round_id=1,
        stock_id=1,
        ticker=ticker,
        side=side,
        quantity=Decimal(qty),
        price=Decimal(price),
        fee=Decimal(fee),
        executed_on=day,
    )


def _flow(fid: int, amount: str, day: date) -> CashFlow:
    return CashFlow(id=fid, round_id=1, amount=Decimal(amount), flowed_on=day)


def _split(ticker: str, day: date, ratio: str) -> SplitEvent:
    return SplitEvent(
        ticker=ticker, effective_on=day, ratio=Decimal(ratio), source="test", ingested_at=_STAMP
    )


_D1 = date(2026, 7, 1)
_D2 = date(2026, 7, 2)
_D3 = date(2026, 7, 3)


def test_replay_deposit_buy_positions_and_cash() -> None:
    days = replay_ledger(
        trades=[_trade(1, "AAA", TradeSide.BUY, "10", "100", _D1, fee="2")],
        flows=[_flow(1, "2000", _D1)],
        splits={},
        grid=[_D1, _D2],
    )
    assert [d.day for d in days] == [_D1, _D2]
    d1 = days[0]
    assert d1.positions == {"AAA": Decimal("10")}
    assert d1.cash == Decimal("998")  # 2000 − 10×100 − fee 2
    assert d1.external_flow == Decimal("2000")  # TWR 분모 보정용
    assert days[1].external_flow == Decimal("0")  # 이후 날 흐름 없음
    assert days[1].positions == {"AAA": Decimal("10")}


def test_replay_intraday_order_split_then_flow_then_trades_by_id() -> None:
    # D2: 2:1 SPLIT(장 시작·보유 10→20) → 입금 → 같은 날 trade 는 id 순(BUY 후 SELL).
    # SELL 15 는 분할 반영 후에만 가능(분할 전 10주면 초과) — 순서 규약이 곧 정합성.
    days = replay_ledger(
        trades=[
            _trade(1, "AAA", TradeSide.BUY, "10", "100", _D1),
            _trade(2, "AAA", TradeSide.BUY, "2", "50", _D2),
            _trade(3, "AAA", TradeSide.SELL, "15", "50", _D2),
        ],
        flows=[_flow(1, "1000", _D1), _flow(2, "100", _D2)],
        splits={"AAA": [_split("AAA", _D2, "2")]},
        grid=[_D1, _D2],
    )
    d2 = days[1]
    # 10(D1) → 분할 20 → +2 → −15 = 7주. 현금 0(D1) → +100 −100(BUY) +750(SELL) = 750.
    assert d2.positions == {"AAA": Decimal("7")}
    assert d2.cash == Decimal("750")
    assert d2.external_flow == Decimal("100")


def test_replay_fractional_split_keeps_decimal_quantity() -> None:
    days = replay_ledger(
        trades=[_trade(1, "AAA", TradeSide.BUY, "3", "100", _D1)],
        flows=[_flow(1, "300", _D1)],
        splits={"AAA": [_split("AAA", _D2, "1.5")]},  # 3:2 분할
        grid=[_D1, _D2],
    )
    assert days[1].positions == {"AAA": Decimal("4.5")}  # 단수주 Decimal 유지(v1 규약)


def test_replay_sell_exceeds_position_raises() -> None:
    with pytest.raises(LedgerError, match="AAA"):
        replay_ledger(
            trades=[
                _trade(1, "AAA", TradeSide.BUY, "5", "100", _D1),
                _trade(2, "AAA", TradeSide.SELL, "6", "100", _D2),
            ],
            flows=[_flow(1, "1000", _D1)],
            splits={},
            grid=[_D1, _D2],
        )


def test_replay_buy_exceeds_cash_raises() -> None:
    # 입금 없이 BUY → 현금 음수 = 명시 실패(DEPOSIT 선행 요구·C-2).
    with pytest.raises(LedgerError, match="현금"):
        replay_ledger(
            trades=[_trade(1, "AAA", TradeSide.BUY, "1", "100", _D1)],
            flows=[],
            splits={},
            grid=[_D1],
        )


def test_replay_withdraw_exceeds_cash_raises() -> None:
    with pytest.raises(LedgerError, match="현금"):
        replay_ledger(
            trades=[],
            flows=[_flow(1, "100", _D1), _flow(2, "-200", _D2)],
            splits={},
            grid=[_D1, _D2],
        )


def test_validate_new_trade_accepts_valid_and_rejects_oversell() -> None:
    trades = [_trade(1, "AAA", TradeSide.BUY, "10", "100", _D1)]
    flows = [_flow(1, "2000", _D1)]
    ok = _trade(None, "AAA", TradeSide.SELL, "10", "110", _D2)
    validate_new_trade(ok, trades=trades, flows=flows, splits={})  # 통과=무예외
    bad = _trade(None, "AAA", TradeSide.SELL, "11", "110", _D2)
    with pytest.raises(LedgerError, match="AAA"):
        validate_new_trade(bad, trades=trades, flows=flows, splits={})


def test_validate_new_trade_same_day_applies_after_existing() -> None:
    # 같은 날 기존 trade(id 有) 뒤에 후보(id=None) 적용 — 같은 날 BUY 후 SELL 허용.
    trades = [_trade(1, "AAA", TradeSide.BUY, "10", "100", _D1)]
    flows = [_flow(1, "1000", _D1)]
    candidate = _trade(None, "AAA", TradeSide.SELL, "10", "100", _D1)
    validate_new_trade(candidate, trades=trades, flows=flows, splits={})  # 무예외


def test_validate_void_rejects_when_later_sell_breaks() -> None:
    # BUY(1) void 하면 뒤 SELL(2) 이 음수 포지션 → 거부.
    trades = [
        _trade(1, "AAA", TradeSide.BUY, "10", "100", _D1),
        _trade(2, "AAA", TradeSide.SELL, "10", "110", _D2),
    ]
    flows = [_flow(1, "2000", _D1)]
    with pytest.raises(LedgerError, match="AAA"):
        validate_void(1, trades=trades, flows=flows, splits={})
    validate_void(2, trades=trades, flows=flows, splits={})  # SELL void 는 안전=무예외


def test_replay_grid_before_events_is_empty_state() -> None:
    days = replay_ledger(
        trades=[_trade(1, "AAA", TradeSide.BUY, "1", "100", _D3)],
        flows=[_flow(1, "100", _D3)],
        splits={},
        grid=[_D1, _D2, _D3],
    )
    assert days[0].positions == {}
    assert days[0].cash == Decimal("0")
    assert days[2].positions == {"AAA": Decimal("1")}
