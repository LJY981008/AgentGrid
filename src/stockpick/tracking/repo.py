"""라운드·거래 저장소 — `RoundRepository` Protocol + PG 구현(사용자 운용 데이터의 1차 진실).

계약(Protocol)은 API 층이 DI 로 주입받고, 테스트는 `fakes.InMemoryRoundRepository` 로 오버라이드
(라이브 0). 두 구현의 의미 동일성은 `tests/test_tracking_repo.py` **공용 contract 테스트**가 봉쇄.

PG 규약(data/db.py 관례): 커서는 `with conn.cursor()`, **커밋은 호출부 책임**(API get_conn 이
요청 단위 commit/rollback — 테스트 rollback 격리 보존), IDENTITY PK 는 `RETURNING id` 회수.
JSONB 직렬화: Decimal→str(정밀도 보존·재구성 시 Decimal 복원 — 조용한 float 강등 금지).

정정 규약(스펙 §3.4): trade/cash_flow 는 append-only — UPDATE 는 soft-void(voided_at·
void_reason)만. 물리 DELETE 금지(감사 보존).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from psycopg.types.json import Json

from .types import (
    CarryInPosition,
    CashFlow,
    PortfolioRound,
    RoundRetrospective,
    RoundStatus,
    SnapshotEntry,
    SplitEvent,
    Trade,
    TradeSide,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from decimal import Decimal

    import psycopg
    from psycopg.rows import TupleRow

logger = logging.getLogger(__name__)


class RoundConflictError(Exception):
    """open 라운드가 이미 존재(전역 1개 — 월 리추얼 강제) 또는 label 중복."""


class RoundRepository(Protocol):
    """라운드·거래·현금흐름·분할 저장 계약 — API DI 지점(구현: Pg·InMemory)."""

    def create_round(self, rnd: PortfolioRound) -> PortfolioRound: ...

    def get_round(self, round_id: int) -> PortfolioRound | None: ...

    def get_open_round(self) -> PortfolioRound | None: ...

    def list_rounds(self) -> list[PortfolioRound]: ...

    def set_top5(self, round_id: int, *, memo: str, top5: Sequence[str]) -> PortfolioRound: ...

    def close_round(
        self,
        round_id: int,
        *,
        retrospective: RoundRetrospective,
        performance_snapshot: dict[str, object],
        closed_at: datetime,
    ) -> PortfolioRound: ...

    def insert_trade(self, trade: Trade) -> Trade: ...

    def insert_cash_flow(self, flow: CashFlow) -> CashFlow: ...

    def void_trade(self, trade_id: int, *, reason: str, at: datetime) -> Trade: ...

    def list_trades(self, *, include_voided: bool = False) -> list[Trade]: ...

    def list_cash_flows(self, *, include_voided: bool = False) -> list[CashFlow]: ...

    def upsert_splits(self, events: Sequence[SplitEvent]) -> int: ...

    def stock_id_for(self, ticker: str) -> int | None: ...

    def delisted_tickers(self, tickers: set[str]) -> set[str]: ...

    def list_splits(self, tickers: set[str]) -> dict[str, list[SplitEvent]]: ...


# ── JSONB 직렬화(Decimal↔str — 정밀도 보존·형상은 이 모듈이 소유) ──────────────


def _dec_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _to_dec(value: object) -> Decimal | None:
    from decimal import Decimal as D

    if value is None:
        return None
    if isinstance(value, str):
        return D(value)
    msg = f"JSONB Decimal 필드가 str 아님(조용한 float 강등 금지): {value!r}"
    raise TypeError(msg)


def snapshot_to_json(entries: Sequence[SnapshotEntry]) -> list[dict[str, object]]:
    return [
        {
            "cik": e.cik,
            "ticker": e.ticker,
            "exchange": e.exchange,
            "rank": e.rank,
            "score": e.score,
            "factors": e.factors,
            "anchor_close": _dec_str(e.anchor_close),
        }
        for e in entries
    ]


def snapshot_from_json(raw: object) -> tuple[SnapshotEntry, ...]:
    if not isinstance(raw, list):
        msg = f"top20_snapshot JSONB 형상 위반(list 아님): {type(raw).__name__}"
        raise TypeError(msg)
    out: list[SnapshotEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            msg = "top20_snapshot 항목이 dict 아님"
            raise TypeError(msg)
        factors_raw = item.get("factors", {})
        factors: dict[str, float] = {}
        if isinstance(factors_raw, dict):
            for k, v in factors_raw.items():
                if isinstance(k, str) and isinstance(v, int | float):
                    factors[k] = float(v)
        out.append(
            SnapshotEntry(
                cik=str(item["cik"]),
                ticker=str(item["ticker"]),
                exchange=str(item["exchange"]),
                rank=int(str(item["rank"])),
                score=float(str(item["score"])),
                factors=factors,
                anchor_close=_to_dec(item.get("anchor_close")),
            )
        )
    return tuple(out)


def carry_in_to_json(positions: Sequence[CarryInPosition]) -> list[dict[str, object]]:
    return [
        {"ticker": p.ticker, "quantity": str(p.quantity), "anchor_close": _dec_str(p.anchor_close)}
        for p in positions
    ]


def carry_in_from_json(raw: object) -> tuple[CarryInPosition, ...]:
    from decimal import Decimal as D

    if not isinstance(raw, list):
        msg = f"carry_in JSONB 형상 위반(list 아님): {type(raw).__name__}"
        raise TypeError(msg)
    out: list[CarryInPosition] = []
    for item in raw:
        if not isinstance(item, dict):
            msg = "carry_in 항목이 dict 아님"
            raise TypeError(msg)
        out.append(
            CarryInPosition(
                ticker=str(item["ticker"]),
                quantity=D(str(item["quantity"])),
                anchor_close=_to_dec(item.get("anchor_close")),
            )
        )
    return tuple(out)


def retro_to_json(retro: RoundRetrospective) -> dict[str, object]:
    return {
        "judgment_good": retro.judgment_good,
        "judgment_bad": retro.judgment_bad,
        "rule_change": retro.rule_change,
    }


def retro_from_json(raw: object) -> RoundRetrospective | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        msg = f"retrospective JSONB 형상 위반: {type(raw).__name__}"
        raise TypeError(msg)
    return RoundRetrospective(
        judgment_good=str(raw["judgment_good"]),
        judgment_bad=str(raw["judgment_bad"]),
        rule_change=str(raw["rule_change"]),
    )


def _obj_dict(raw: object) -> dict[str, object] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        msg = f"JSONB dict 형상 위반: {type(raw).__name__}"
        raise TypeError(msg)
    return {str(k): v for k, v in raw.items()}


# ── PG 구현 ──────────────────────────────────────────────────────────────────

_ROUND_COLS = (
    "id, label, status, opened_on, anchor_as_of, top20_snapshot, rule_signature, validated, "
    "g7_summary, carry_in, discussion_memo, top5, retrospective, performance_snapshot, closed_at"
)
_TRADE_COLS = (
    "id, round_id, stock_id, ticker, side, quantity, price, fee, executed_on, note, "
    "voided_at, void_reason"
)
_FLOW_COLS = "id, round_id, amount, flowed_on, note, voided_at, void_reason"


class PgRoundRepository:
    """PG 저장 구현 — conn 주입(수명·커밋은 호출부: API get_conn / 테스트 rollback)."""

    def __init__(self, conn: psycopg.Connection[TupleRow]) -> None:
        self._conn = conn

    # -- rounds --

    def create_round(self, rnd: PortfolioRound) -> PortfolioRound:
        if self.get_open_round() is not None:
            msg = "open 라운드가 이미 존재 — close 후 새 라운드(월 리추얼·전역 1개)"
            raise RoundConflictError(msg)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO portfolio_round (
                    label, status, opened_on, anchor_as_of, top20_snapshot, rule_signature,
                    validated, g7_summary, carry_in, discussion_memo, top5
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    rnd.label,
                    rnd.status.value,
                    rnd.opened_on,
                    rnd.anchor_as_of,
                    Json(snapshot_to_json(rnd.top20_snapshot)),
                    rnd.rule_signature,
                    rnd.validated,
                    None if rnd.g7_summary is None else Json(rnd.g7_summary),
                    Json(carry_in_to_json(rnd.carry_in)),
                    rnd.discussion_memo,
                    Json(list(rnd.top5)),
                ),
            )
            row = cur.fetchone()
            if row is None:  # pragma: no cover - RETURNING 은 항상 1행
                msg = "INSERT RETURNING 이 행을 반환하지 않음"
                raise RuntimeError(msg)
            round_id = int(row[0])
        logger.info("라운드 생성: id=%d label=%s", round_id, rnd.label)
        created = self.get_round(round_id)
        if created is None:  # pragma: no cover - 방금 INSERT
            msg = f"생성 직후 라운드 조회 실패: id={round_id}"
            raise RuntimeError(msg)
        return created

    def get_round(self, round_id: int) -> PortfolioRound | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {_ROUND_COLS} FROM portfolio_round WHERE id = %s",  # noqa: S608
                (round_id,),
            )
            row = cur.fetchone()
        return None if row is None else self._row_to_round(row)

    def get_open_round(self) -> PortfolioRound | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {_ROUND_COLS} FROM portfolio_round WHERE status = 'open'"  # noqa: S608
            )
            row = cur.fetchone()
        return None if row is None else self._row_to_round(row)

    def list_rounds(self) -> list[PortfolioRound]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {_ROUND_COLS} FROM portfolio_round ORDER BY opened_on, id"  # noqa: S608
            )
            rows = cur.fetchall()
        return [self._row_to_round(row) for row in rows]

    def set_top5(self, round_id: int, *, memo: str, top5: Sequence[str]) -> PortfolioRound:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE portfolio_round SET discussion_memo = %s, top5 = %s "
                "WHERE id = %s AND status = 'open' RETURNING id",
                (memo, Json(list(top5)), round_id),
            )
            if cur.fetchone() is None:
                msg = f"open 라운드 아님(또는 부재): id={round_id}"
                raise ValueError(msg)
        updated = self.get_round(round_id)
        if updated is None:  # pragma: no cover - 방금 UPDATE 성공
            msg = f"갱신 직후 라운드 조회 실패: id={round_id}"
            raise RuntimeError(msg)
        return updated

    def close_round(
        self,
        round_id: int,
        *,
        retrospective: RoundRetrospective,
        performance_snapshot: dict[str, object],
        closed_at: datetime,
    ) -> PortfolioRound:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE portfolio_round SET status = 'closed', retrospective = %s, "
                "performance_snapshot = %s, closed_at = %s "
                "WHERE id = %s AND status = 'open' RETURNING id",
                (
                    Json(retro_to_json(retrospective)),
                    Json(performance_snapshot),
                    closed_at,
                    round_id,
                ),
            )
            if cur.fetchone() is None:
                msg = f"open 라운드 아님(또는 부재) — close 불가: id={round_id}"
                raise ValueError(msg)
        logger.info("라운드 마감: id=%d", round_id)
        closed = self.get_round(round_id)
        if closed is None:  # pragma: no cover
            msg = f"마감 직후 라운드 조회 실패: id={round_id}"
            raise RuntimeError(msg)
        return closed

    # -- trades / cash flows --

    def insert_trade(self, trade: Trade) -> Trade:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trade (
                    round_id, stock_id, ticker, side, quantity, price, fee, executed_on, note
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    trade.round_id,
                    trade.stock_id,
                    trade.ticker,
                    trade.side.value,
                    trade.quantity,
                    trade.price,
                    trade.fee,
                    trade.executed_on,
                    trade.note,
                ),
            )
            row = cur.fetchone()
            if row is None:  # pragma: no cover
                msg = "INSERT RETURNING 이 행을 반환하지 않음"
                raise RuntimeError(msg)
        from dataclasses import replace

        return replace(trade, id=int(row[0]))

    def insert_cash_flow(self, flow: CashFlow) -> CashFlow:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cash_flow (round_id, amount, flowed_on, note) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (flow.round_id, flow.amount, flow.flowed_on, flow.note),
            )
            row = cur.fetchone()
            if row is None:  # pragma: no cover
                msg = "INSERT RETURNING 이 행을 반환하지 않음"
                raise RuntimeError(msg)
        from dataclasses import replace

        return replace(flow, id=int(row[0]))

    def void_trade(self, trade_id: int, *, reason: str, at: datetime) -> Trade:
        with self._conn.cursor() as cur:
            cur.execute(
                f"UPDATE trade SET voided_at = %s, void_reason = %s "  # noqa: S608
                f"WHERE id = %s AND voided_at IS NULL RETURNING {_TRADE_COLS}",
                (at, reason, trade_id),
            )
            row = cur.fetchone()
        if row is None:
            msg = f"void 대상 trade 부재(또는 이미 void): id={trade_id}"
            raise ValueError(msg)
        logger.info("trade void: id=%d 사유=%s", trade_id, reason)
        return self._row_to_trade(row)

    def list_trades(self, *, include_voided: bool = False) -> list[Trade]:
        cond = "" if include_voided else "WHERE voided_at IS NULL "
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {_TRADE_COLS} FROM trade {cond}ORDER BY executed_on, id"  # noqa: S608
            )
            rows = cur.fetchall()
        return [self._row_to_trade(row) for row in rows]

    def list_cash_flows(self, *, include_voided: bool = False) -> list[CashFlow]:
        cond = "" if include_voided else "WHERE voided_at IS NULL "
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {_FLOW_COLS} FROM cash_flow {cond}ORDER BY flowed_on, id"  # noqa: S608
            )
            rows = cur.fetchall()
        return [self._row_to_flow(row) for row in rows]

    # -- stock 마스터 참조(FK 해소·폐지 판정) --

    def stock_id_for(self, ticker: str) -> int | None:
        """ticker → stock.id(FK 해소). 다중 행(재상장 등)은 active 우선·최신 id. 부재=None."""
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM stock WHERE ticker = %s "
                "ORDER BY (listing_status = 'active') DESC, id DESC LIMIT 1",
                (ticker,),
            )
            row = cur.fetchone()
        return None if row is None else int(row[0])

    def delisted_tickers(self, tickers: set[str]) -> set[str]:
        """주어진 집합 중 폐지(listing_status='delisted') 종목 — 성과 as-of·청산 규약 입력."""
        if not tickers:
            return set()
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT ticker FROM stock WHERE ticker = ANY(%s) AND listing_status = 'delisted'",
                (sorted(tickers),),
            )
            rows = cur.fetchall()
        return {str(row[0]) for row in rows}

    # -- splits --

    def upsert_splits(self, events: Sequence[SplitEvent]) -> int:
        if not events:
            return 0
        with self._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO corporate_action
                    (ticker, effective_on, kind, ratio, source, ingested_at)
                VALUES (%s, %s, 'split', %s, %s, %s)
                ON CONFLICT (ticker, effective_on) DO UPDATE
                    SET ratio = EXCLUDED.ratio, source = EXCLUDED.source,
                        ingested_at = EXCLUDED.ingested_at
                """,
                [(e.ticker, e.effective_on, e.ratio, e.source, e.ingested_at) for e in events],
            )
        logger.info("분할 이벤트 upsert: %d건", len(events))
        return len(events)

    def list_splits(self, tickers: set[str]) -> dict[str, list[SplitEvent]]:
        if not tickers:
            return {}
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT ticker, effective_on, ratio, source, ingested_at FROM corporate_action "
                "WHERE ticker = ANY(%s) AND kind = 'split' ORDER BY ticker, effective_on",
                (sorted(tickers),),
            )
            rows = cur.fetchall()
        out: dict[str, list[SplitEvent]] = {}
        for ticker, effective_on, ratio, source, ingested_at in rows:
            out.setdefault(str(ticker), []).append(
                SplitEvent(
                    ticker=str(ticker),
                    effective_on=effective_on,
                    ratio=ratio,
                    source=str(source),
                    ingested_at=ingested_at,
                )
            )
        return out

    # -- row mapping --

    @staticmethod
    def _row_to_round(row: TupleRow) -> PortfolioRound:
        (
            round_id,
            label,
            status,
            opened_on,
            anchor_as_of,
            top20_snapshot,
            rule_signature,
            validated,
            g7_summary,
            carry_in,
            discussion_memo,
            top5,
            retrospective,
            performance_snapshot,
            closed_at,
        ) = row
        top5_list: tuple[str, ...] = ()
        if isinstance(top5, list):
            top5_list = tuple(str(t) for t in top5)
        return PortfolioRound(
            id=int(round_id),
            label=str(label),
            status=RoundStatus(str(status)),
            opened_on=opened_on,
            anchor_as_of=anchor_as_of,
            top20_snapshot=snapshot_from_json(top20_snapshot),
            rule_signature=str(rule_signature),
            validated=bool(validated),
            g7_summary=_obj_dict(g7_summary),
            carry_in=carry_in_from_json(carry_in),
            discussion_memo=None if discussion_memo is None else str(discussion_memo),
            top5=top5_list,
            retrospective=retro_from_json(retrospective),
            performance_snapshot=_obj_dict(performance_snapshot),
            closed_at=closed_at,
        )

    @staticmethod
    def _row_to_trade(row: TupleRow) -> Trade:
        (
            trade_id,
            round_id,
            stock_id,
            ticker,
            side,
            quantity,
            price,
            fee,
            executed_on,
            note,
            voided_at,
            void_reason,
        ) = row
        return Trade(
            id=int(trade_id),
            round_id=int(round_id),
            stock_id=int(stock_id),
            ticker=str(ticker),
            side=TradeSide(str(side)),
            quantity=quantity,
            price=price,
            fee=fee,
            executed_on=executed_on,
            note=None if note is None else str(note),
            voided_at=voided_at,
            void_reason=None if void_reason is None else str(void_reason),
        )

    @staticmethod
    def _row_to_flow(row: TupleRow) -> CashFlow:
        flow_id, round_id, amount, flowed_on, note, voided_at, void_reason = row
        return CashFlow(
            id=int(flow_id),
            round_id=int(round_id),
            amount=amount,
            flowed_on=flowed_on,
            note=None if note is None else str(note),
            voided_at=voided_at,
            void_reason=None if void_reason is None else str(void_reason),
        )
