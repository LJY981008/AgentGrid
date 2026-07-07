"""테스트용 InMemory 저장소 — `RoundRepository` 계약의 메모리 구현(라이브·PG 0).

의미 동일성은 tests/test_tracking_repo.py contract 테스트(parametrize)가 Pg 구현과 함께 봉쇄.
API 테스트는 dependency_overrides 로 이 구현을 주입(backtest/fakes.py 선례).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .repo import RoundConflictError
from .types import CashFlow, PortfolioRound, RoundStatus, SplitEvent, Trade

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from .types import RoundRetrospective


class InMemoryRoundRepository:
    """dict 기반 — id 자동 증가·open 유일·soft-void·splits 멱등(계약 동형)."""

    def __init__(self) -> None:
        self._rounds: dict[int, PortfolioRound] = {}
        self._trades: dict[int, Trade] = {}
        self._flows: dict[int, CashFlow] = {}
        self._splits: dict[tuple[str, object], SplitEvent] = {}
        self._next_id = 1

    def _new_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    # -- rounds --

    def create_round(self, rnd: PortfolioRound) -> PortfolioRound:
        if self.get_open_round() is not None:
            msg = "open 라운드가 이미 존재 — close 후 새 라운드(월 리추얼·전역 1개)"
            raise RoundConflictError(msg)
        new_id = self._new_id()
        created = replace(rnd, id=new_id)
        self._rounds[new_id] = created
        return created

    def get_round(self, round_id: int) -> PortfolioRound | None:
        return self._rounds.get(round_id)

    def get_open_round(self) -> PortfolioRound | None:
        for rnd in self._rounds.values():
            if rnd.status is RoundStatus.OPEN:
                return rnd
        return None

    def list_rounds(self) -> list[PortfolioRound]:
        return sorted(self._rounds.values(), key=lambda r: (r.opened_on, r.id or 0))

    def set_top5(self, round_id: int, *, memo: str, top5: Sequence[str]) -> PortfolioRound:
        rnd = self._rounds.get(round_id)
        if rnd is None or rnd.status is not RoundStatus.OPEN:
            msg = f"open 라운드 아님(또는 부재): id={round_id}"
            raise ValueError(msg)
        updated = replace(rnd, discussion_memo=memo, top5=tuple(top5))
        self._rounds[round_id] = updated
        return updated

    def close_round(
        self,
        round_id: int,
        *,
        retrospective: RoundRetrospective,
        performance_snapshot: dict[str, object],
        closed_at: datetime,
    ) -> PortfolioRound:
        rnd = self._rounds.get(round_id)
        if rnd is None or rnd.status is not RoundStatus.OPEN:
            msg = f"open 라운드 아님(또는 부재) — close 불가: id={round_id}"
            raise ValueError(msg)
        closed = replace(
            rnd,
            status=RoundStatus.CLOSED,
            retrospective=retrospective,
            performance_snapshot=dict(performance_snapshot),
            closed_at=closed_at,
        )
        self._rounds[round_id] = closed
        return closed

    # -- trades / cash flows --

    def insert_trade(self, trade: Trade) -> Trade:
        new_id = self._new_id()
        created = replace(trade, id=new_id)
        self._trades[new_id] = created
        return created

    def insert_cash_flow(self, flow: CashFlow) -> CashFlow:
        new_id = self._new_id()
        created = replace(flow, id=new_id)
        self._flows[new_id] = created
        return created

    def void_trade(self, trade_id: int, *, reason: str, at: datetime) -> Trade:
        trade = self._trades.get(trade_id)
        if trade is None or trade.voided_at is not None:
            msg = f"void 대상 trade 부재(또는 이미 void): id={trade_id}"
            raise ValueError(msg)
        voided = replace(trade, voided_at=at, void_reason=reason)
        self._trades[trade_id] = voided
        return voided

    def list_trades(self, *, include_voided: bool = False) -> list[Trade]:
        trades = [
            t for t in self._trades.values() if include_voided or t.voided_at is None
        ]
        return sorted(trades, key=lambda t: (t.executed_on, t.id or 0))

    def list_cash_flows(self, *, include_voided: bool = False) -> list[CashFlow]:
        flows = [f for f in self._flows.values() if include_voided or f.voided_at is None]
        return sorted(flows, key=lambda f: (f.flowed_on, f.id or 0))

    # -- splits --

    def upsert_splits(self, events: Sequence[SplitEvent]) -> int:
        for ev in events:
            self._splits[(ev.ticker, ev.effective_on)] = ev  # (ticker, 일자) 멱등 갱신
        return len(events)

    def list_splits(self, tickers: set[str]) -> dict[str, list[SplitEvent]]:
        out: dict[str, list[SplitEvent]] = {}
        for ev in self._splits.values():
            if ev.ticker in tickers:
                out.setdefault(ev.ticker, []).append(ev)
        for events in out.values():
            events.sort(key=lambda e: e.effective_on)
        return out
