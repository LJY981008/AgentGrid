"""tracking repo contract 테스트 — InMemory·Pg **동일 계약**(parametrize·드리프트 봉쇄).

Pg 는 compose postgres(라이브 외부데이터 0·PG=로컬 인프라). DATABASE_URL 미연결 시 skip.
각 테스트 rollback 격리(test_db.py 패턴). 검증: 라운드 왕복(JSONB Decimal 재구성 포함)·
open 유일성·soft-void(기본 제외)·close 상태 전이·splits 멱등.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest
from psycopg.rows import TupleRow

from stockpick.data import db
from stockpick.tracking.fakes import InMemoryRoundRepository
from stockpick.tracking.repo import PgRoundRepository, RoundConflictError, RoundRepository
from stockpick.tracking.types import (
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

_STAMP = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


def _entry(ticker: str, rank: int, *, close: str | None = "100.5") -> SnapshotEntry:
    return SnapshotEntry(
        cik=f"000000000{rank}",
        ticker=ticker,
        exchange="NASDAQ",
        rank=rank,
        score=0.5 - rank * 0.01,
        factors={"momentum": 0.5, "roe": 0.12},
        anchor_close=None if close is None else Decimal(close),
    )


def _round(label: str = "2026-07") -> PortfolioRound:
    return PortfolioRound(
        id=None,
        label=label,
        status=RoundStatus.OPEN,
        opened_on=date(2026, 7, 1),
        anchor_as_of=date(2026, 6, 30),
        top20_snapshot=(_entry("AAA", 1), _entry("BBB", 2, close=None)),
        rule_signature="SIG",
        validated=False,
        g7_summary={"passed": False, "reason": "가격<=0 잔존"},
        carry_in=(CarryInPosition(ticker="CCC", quantity=Decimal("3.5"), anchor_close=None),),
    )


def _trade(round_id: int, *, ticker: str = "AAA", day: int = 2) -> Trade:
    return Trade(
        id=None,
        round_id=round_id,
        stock_id=_STOCK_IDS[ticker],
        ticker=ticker,
        side=TradeSide.BUY,
        quantity=Decimal("10"),
        price=Decimal("100.25"),
        fee=Decimal("1.5"),
        executed_on=date(2026, 7, day),
    )


_STOCK_IDS: dict[str, int] = {}  # Pg 픽스처가 실 stock.id 채움(InMemory 는 임의값)


@pytest.fixture
def pg_conn() -> Iterator[psycopg.Connection[TupleRow]]:
    try:
        c = db.connect()
    except (RuntimeError, psycopg.OperationalError) as exc:
        pytest.skip(f"PG 미연결 — tracking Pg 테스트 skip: {exc!r}")
    try:
        with c.cursor() as cur:
            cur.execute("TRUNCATE portfolio_round, trade, cash_flow, corporate_action CASCADE")
        yield c
        c.rollback()
    finally:
        c.close()


@pytest.fixture(params=["memory", "pg"])
def repo(request: pytest.FixtureRequest) -> RoundRepository:
    _STOCK_IDS.clear()
    if request.param == "memory":
        _STOCK_IDS.update({"AAA": 1, "BBB": 2, "CCC": 3})
        return InMemoryRoundRepository()
    conn: psycopg.Connection[TupleRow] = request.getfixturevalue("pg_conn")
    with conn.cursor() as cur:  # trade.stock_id FK 충족용 최소 마스터
        for t in ("AAA", "BBB", "CCC"):
            cur.execute(
                "INSERT INTO stock (ticker, name, exchange, source, ingested_at) "
                "VALUES (%s, %s, 'NASDAQ', 'test', %s) RETURNING id",
                (t, t, _STAMP),
            )
            row = cur.fetchone()
            assert row is not None
            _STOCK_IDS[t] = int(row[0])
    return PgRoundRepository(conn)


def test_create_and_get_round_roundtrip(repo: RoundRepository) -> None:
    created = repo.create_round(_round())
    assert created.id is not None
    got = repo.get_round(created.id)
    assert got is not None
    # 전 필드 왕복(JSONB Decimal 재구성 포함) — id 만 다르고 원본과 동일 내용.
    assert got.label == "2026-07"
    assert got.top20_snapshot == _round().top20_snapshot  # anchor_close Decimal 보존
    assert got.carry_in == _round().carry_in
    assert got.g7_summary == {"passed": False, "reason": "가격<=0 잔존"}
    assert got.status is RoundStatus.OPEN
    assert repo.get_open_round() == got


def test_second_open_round_conflicts(repo: RoundRepository) -> None:
    repo.create_round(_round("2026-07"))
    with pytest.raises(RoundConflictError):
        repo.create_round(_round("2026-08"))  # open 전역 1개(리추얼 강제)


def test_set_top5_and_memo(repo: RoundRepository) -> None:
    rnd = repo.create_round(_round())
    assert rnd.id is not None
    updated = repo.set_top5(rnd.id, memo="토의 요약", top5=("AAA", "BBB"))
    assert updated.top5 == ("AAA", "BBB")
    assert updated.discussion_memo == "토의 요약"


def test_trades_roundtrip_ordered_and_void(repo: RoundRepository) -> None:
    rnd = repo.create_round(_round())
    assert rnd.id is not None
    t2 = repo.insert_trade(_trade(rnd.id, day=3))
    t1 = repo.insert_trade(_trade(rnd.id, day=2))
    assert t1.id is not None and t2.id is not None
    listed = repo.list_trades()
    assert [t.executed_on.day for t in listed] == [2, 3]  # executed_on, id 순(전역 원장)
    voided = repo.void_trade(t1.id, reason="수량 오타", at=_STAMP)
    assert voided.voided_at is not None
    assert voided.void_reason == "수량 오타"
    assert [t.id for t in repo.list_trades()] == [t2.id]  # 기본 voided 제외
    assert len(repo.list_trades(include_voided=True)) == 2


def test_void_missing_trade_raises(repo: RoundRepository) -> None:
    with pytest.raises(ValueError, match="trade"):
        repo.void_trade(99999, reason="없음", at=_STAMP)


def test_cash_flows_roundtrip(repo: RoundRepository) -> None:
    rnd = repo.create_round(_round())
    assert rnd.id is not None
    flow = repo.insert_cash_flow(
        CashFlow(id=None, round_id=rnd.id, amount=Decimal("1000"), flowed_on=date(2026, 7, 1))
    )
    assert flow.id is not None
    flows = repo.list_cash_flows()
    assert len(flows) == 1
    assert flows[0].amount == Decimal("1000")


def test_close_round_transitions_and_frees_open_slot(repo: RoundRepository) -> None:
    rnd = repo.create_round(_round())
    assert rnd.id is not None
    retro = RoundRetrospective(
        judgment_good="분산 유지", judgment_bad="추격 매수", rule_change="없음"
    )
    closed = repo.close_round(
        rnd.id,
        retrospective=retro,
        performance_snapshot={"as_of": "2026-07-31", "actual_twr": "0.021"},
        closed_at=_STAMP,
    )
    assert closed.status is RoundStatus.CLOSED
    assert closed.retrospective == retro
    assert closed.performance_snapshot == {"as_of": "2026-07-31", "actual_twr": "0.021"}
    assert closed.closed_at is not None
    assert repo.get_open_round() is None
    repo.create_round(_round("2026-08"))  # close 후 새 라운드 가능


def test_upsert_splits_idempotent(repo: RoundRepository) -> None:
    ev = SplitEvent(
        ticker="AAA", effective_on=date(2026, 7, 10), ratio=Decimal("2"), source="eodhd",
        ingested_at=_STAMP,
    )
    assert repo.upsert_splits([ev]) == 1
    revised = SplitEvent(
        ticker="AAA", effective_on=date(2026, 7, 10), ratio=Decimal("4"), source="eodhd",
        ingested_at=_STAMP,
    )
    repo.upsert_splits([revised])  # 같은 (ticker, effective_on) → 갱신(멱등)
    splits = repo.list_splits({"AAA", "ZZZ"})
    assert set(splits) == {"AAA"}
    assert len(splits["AAA"]) == 1
    assert splits["AAA"][0].ratio == Decimal("4")
