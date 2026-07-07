"""전역 포지션 원장 — trade·현금흐름·SPLIT 이벤트 재생(replay)·불변식 검증(스펙 §3.3).

**일중 순서 규약(결정성·동결)**: 하루 d 처리 = ① `effective_on == d` SPLIT 로 보유수량 × ratio
(장 시작 효력 — acceptance 실측: EODHD effective_on = 분할 후 첫 거래일·당일 가격 이미 반영)
→ ② 외부 현금흐름(start-of-day) → ③ 당일 trade 를 id 오름차순 적용 → ④ 평가는 당일 종가
(performance 층 책임). 불변식: 모든 시점 positions ≥ 0, cash ≥ 0 — 위반 = `LedgerError`
명시 실패(API 422 매핑·조용한 음수 금지).

⚠️ 수량 보정은 **SPLIT 이벤트만** — `adj_factor`(분할+배당 혼합)를 쓰면 배당락마다 유령
수량이 생긴다(스펙 §3.1 BLOCKING). 순수 함수(I/O 없음) — voided 제외는 repo 조회 책임.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from .types import Trade, TradeSide

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date

    from .types import CashFlow, SplitEvent


class LedgerError(Exception):
    """원장 불변식 위반(SELL 초과·현금 음수) — 어느 종목·어느 날짜·왜 를 담은 명시 실패."""


@dataclass(frozen=True, slots=True)
class LedgerDay:
    """평가 그리드 하루의 원장 상태 — 수량(SPLIT 반영)·현금·당일 외부 순유출입(TWR 분모)."""

    day: date
    positions: dict[str, Decimal]
    cash: Decimal
    external_flow: Decimal


def _sorted_events(
    trades: Sequence[Trade],
    flows: Sequence[CashFlow],
    splits: Mapping[str, Sequence[SplitEvent]],
) -> tuple[list[Trade], list[CashFlow], list[SplitEvent]]:
    """이벤트 정렬 — trade 는 (executed_on, id·None=해당일 마지막), flow/split 은 일자순."""
    # id=None(미영속 후보)은 같은 날 기존 trade 뒤에 적용 — validate_new_trade 규약.
    trades_sorted = sorted(
        trades, key=lambda t: (t.executed_on, t.id if t.id is not None else float("inf"))
    )
    flows_sorted = sorted(flows, key=lambda f: (f.flowed_on, f.id if f.id is not None else 0))
    splits_sorted = sorted(
        (ev for events in splits.values() for ev in events),
        key=lambda ev: (ev.effective_on, ev.ticker),
    )
    return trades_sorted, flows_sorted, splits_sorted


def replay_ledger(
    trades: Sequence[Trade],
    flows: Sequence[CashFlow],
    splits: Mapping[str, Sequence[SplitEvent]],
    grid: Sequence[date],
) -> list[LedgerDay]:
    """전 이벤트를 일자순 재생해 grid 각 날의 원장 상태 반환(grid 오름차순 가정).

    grid 밖(사이) 일자의 이벤트도 시간순으로 전부 적용 — grid 는 **평가 시점 선택**일 뿐
    상태 누적과 무관. grid[i] 의 external_flow = (grid[i-1], grid[i]] 구간 순유출입
    (첫 grid 는 그 이전 전부) — TWR 분모 보정 `V/(V_prev + F)` 용.
    """
    trades_sorted, flows_sorted, splits_sorted = _sorted_events(trades, flows, splits)

    positions: dict[str, Decimal] = {}
    cash = Decimal(0)
    ti = fi = si = 0
    out: list[LedgerDay] = []
    flow_since_last_grid = Decimal(0)

    # 이벤트 일자 ∪ grid 를 시간순으로 소진 — grid 날마다 스냅샷.
    event_days = sorted(
        {t.executed_on for t in trades_sorted}
        | {f.flowed_on for f in flows_sorted}
        | {s.effective_on for s in splits_sorted}
        | set(grid)
    )
    grid_iter = iter(grid)
    next_grid = next(grid_iter, None)

    for day in event_days:
        # ① SPLIT(장 시작) — 보유수량 × ratio(보유 없으면 no-op).
        while si < len(splits_sorted) and splits_sorted[si].effective_on == day:
            ev = splits_sorted[si]
            si += 1
            held = positions.get(ev.ticker)
            if held is not None and held > 0:
                positions[ev.ticker] = held * ev.ratio
        # ② 외부 현금흐름(start-of-day).
        while fi < len(flows_sorted) and flows_sorted[fi].flowed_on == day:
            flow = flows_sorted[fi]
            fi += 1
            cash += flow.amount
            flow_since_last_grid += flow.amount
            if cash < 0:
                msg = (
                    f"현금 음수: {day} 유출 {flow.amount} 적용 후 {cash} "
                    f"(출금이 잔고 초과 — 조용한 음수 금지)"
                )
                raise LedgerError(msg)
        # ③ trade(id 오름차순).
        while ti < len(trades_sorted) and trades_sorted[ti].executed_on == day:
            trade = trades_sorted[ti]
            ti += 1
            _apply_trade(positions, trade, day)
            cash = _apply_cash(cash, trade, day)

        # ④ grid 날이면 스냅샷(평가는 performance 층).
        while next_grid is not None and next_grid == day:
            out.append(
                LedgerDay(
                    day=day,
                    positions={t: q for t, q in positions.items() if q > 0},
                    cash=cash,
                    external_flow=flow_since_last_grid,
                )
            )
            flow_since_last_grid = Decimal(0)
            next_grid = next(grid_iter, None)

    return out


def _apply_trade(positions: dict[str, Decimal], trade: Trade, day: date) -> None:
    held = positions.get(trade.ticker, Decimal(0))
    if trade.side is TradeSide.BUY:
        positions[trade.ticker] = held + trade.quantity
        return
    remaining = held - trade.quantity
    if remaining < 0:
        msg = (
            f"SELL 초과: {trade.ticker} {day} 보유 {held} < 매도 {trade.quantity} "
            f"(분할 반영 후 수량 기준 — 조용한 음수 포지션 금지)"
        )
        raise LedgerError(msg)
    positions[trade.ticker] = remaining


def _apply_cash(cash: Decimal, trade: Trade, day: date) -> Decimal:
    if trade.side is TradeSide.BUY:
        cash -= trade.quantity * trade.price + trade.fee
    else:
        cash += trade.quantity * trade.price - trade.fee
    if cash < 0:
        msg = (
            f"현금 음수: {trade.ticker} {day} {trade.side.value} 적용 후 {cash} "
            f"(입금(DEPOSIT) 선행 필요 — 조용한 음수 금지)"
        )
        raise LedgerError(msg)
    return cash


def validate_new_trade(
    candidate: Trade,
    *,
    trades: Sequence[Trade],
    flows: Sequence[CashFlow],
    splits: Mapping[str, Sequence[SplitEvent]],
) -> None:
    """신규 trade 후보를 전역 원장 재생으로 검증 — 위반 시 LedgerError(통과=무예외).

    후보(id=None)는 같은 날 기존 trade 뒤에 적용(_sorted_events 규약). API 가 422 매핑.
    """
    combined = [*trades, candidate]
    horizon = max(t.executed_on for t in combined)
    replay_ledger(combined, flows, splits, grid=[horizon])


def validate_void(
    target_id: int,
    *,
    trades: Sequence[Trade],
    flows: Sequence[CashFlow],
    splits: Mapping[str, Sequence[SplitEvent]],
) -> None:
    """trade void 후보 검증 — 제거 후 재생이 불변식을 깨면 LedgerError(후속 SELL 음수화 차단)."""
    remaining = [t for t in trades if t.id != target_id]
    if len(remaining) == len(trades):
        msg = f"void 대상 trade 부재: id={target_id}"
        raise ValueError(msg)
    if not remaining and not flows:
        return
    dates = [t.executed_on for t in remaining] + [f.flowed_on for f in flows]
    replay_ledger(remaining, flows, splits, grid=[max(dates)])
