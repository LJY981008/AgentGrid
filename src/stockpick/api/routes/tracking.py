"""추적·보정 루프 API(M4) — 라운드·거래·성과·마감(스펙 §6).

상태 규약: open 라운드 전역 1개(409)·close 후 불변(void 409)·거래는 Top5 확정 후(422)·
executed_on ∈ [opened_on, today](422)·원장 불변식 위반 422(LedgerError — SELL 초과·현금 음수)·
close 는 신선도 게이트(stale→409 "수집 먼저")+구조화 회고 필수+성과 스냅샷 동결.

⭐ §4.1 BLOCKING: 라운드의 validated/warning 은 **생성 시점 스냅샷 값 동결**(미래 룰 검증과
무관 — 과거 라운드 라벨 불변). 성과 응답도 동일 맥락 노출 + `return_convention="price"`
(배당 미반영) 명시 — 무표기 척도 혼합 차단.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — Depends 런타임 타입
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from ...backtest.s6_gate import ranking_rule_signature
from ...data.benchmark import BENCHMARK_SUBDIR, BENCHMARK_TICKER, sync_benchmark_prices
from ...data.price_read import load_raw_close_range
from ...rules._scan import load_close_as_of
from ...tracking.ledger import LedgerError, replay_ledger, validate_new_trade, validate_void
from ...tracking.performance import (
    PerformanceUnmeasurableError,
    RoundPerformance,
    compute_round_performance,
)
from ...tracking.repo import RoundConflictError, RoundRepository
from ...tracking.types import (
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
from ..deps import get_base_dir, get_identity_resolver, get_round_repo, get_source
from ..models import (
    BenchmarkSyncResponse,
    CarryInModel,
    CashFlowCreateRequest,
    CashFlowModel,
    ContributionModel,
    PerformanceResponse,
    PerfPoint,
    RetrospectiveModel,
    RoundCreateRequest,
    RoundListItem,
    RoundModel,
    SeriesPerfModel,
    SlippageModel,
    SnapshotEntryModel,
    Top5Request,
    TradeCreateRequest,
    TradeModel,
    VoidRequest,
)
from ..ranking_service import WARNING_UNVALIDATED, WARNING_VALIDATED, compute_ranking

if TYPE_CHECKING:
    from ...backtest.ports import IdentityResolver
    from ...data.source import DataSource
    from ...tracking.performance import SeriesPerf

logger = logging.getLogger(__name__)

router = APIRouter()

_SNAPSHOT_TOP_N = 20  # 기획 §3-3 — 정량 Top20 스크리닝
_SNAPSHOT_LOOKBACK = 126
_SNAPSHOT_SKIP = 21


def _warning(validated: bool) -> str:  # noqa: FBT001 — 내부 헬퍼(표시 문자열 선택)
    return WARNING_VALIDATED if validated else WARNING_UNVALIDATED


# ── 라운드 생성·조회 ─────────────────────────────────────────────────────────


@router.post("/rounds", response_model=RoundModel)
def create_round(
    body: RoundCreateRequest,
    base_dir: Path = Depends(get_base_dir),
    identity: IdentityResolver = Depends(get_identity_resolver),
    repo: RoundRepository = Depends(get_round_repo),
) -> RoundModel:
    """라운드 생성 — 현 랭킹 Top20 스냅샷 자동 캡처(+anchor_close 동결)·carry-in 파생.

    스냅샷 = ranking_service.compute_ranking(랭킹 화면과 단일 출처·group=all·top20).
    validated/warning 은 이 시점 값으로 동결(정직성 — 미래 룰 검증과 무관).
    """
    ranking = compute_ranking(
        base_dir,
        identity,
        as_of=body.as_of,
        lookback_days=_SNAPSHOT_LOOKBACK,
        skip_recent_days=_SNAPSHOT_SKIP,
        top_n=_SNAPSHOT_TOP_N,
        group="all",
    )
    if ranking.meta.as_of is None or not ranking.entries:
        raise HTTPException(
            status_code=422, detail="랭킹 산출 불가(데이터 없음) — 수집 먼저(/api/ingest)"
        )
    anchor_as_of = ranking.meta.as_of
    raw_close = load_close_as_of(base_dir, as_of=anchor_as_of)
    snapshot = tuple(
        SnapshotEntry(
            cik=e.cik,
            ticker=e.ticker,
            exchange=e.exchange.value,
            rank=e.rank,
            score=e.score,
            factors=dict(e.factors),
            anchor_close=raw_close.get(e.ticker),
        )
        for e in ranking.entries
    )
    # carry-in — 전역 원장 재생 현재 포지션(open 시점 동결·리포팅 앵커). 첫 라운드 = 빈.
    trades = repo.list_trades()
    flows = repo.list_cash_flows()
    carry: tuple[CarryInPosition, ...] = ()
    if trades:
        splits = repo.list_splits({t.ticker for t in trades})
        horizon = max(
            [t.executed_on for t in trades] + [f.flowed_on for f in flows] + [anchor_as_of]
        )
        ledger = replay_ledger(trades, flows, splits, grid=[horizon])
        positions = ledger[-1].positions if ledger else {}
        carry = tuple(
            CarryInPosition(ticker=t, quantity=q, anchor_close=raw_close.get(t))
            for t, q in sorted(positions.items())
        )

    rnd = PortfolioRound(
        id=None,
        label=body.label,
        status=RoundStatus.OPEN,
        opened_on=datetime.now(tz=UTC).date(),
        anchor_as_of=anchor_as_of,
        top20_snapshot=snapshot,
        rule_signature=ranking_rule_signature(
            lookback_days=_SNAPSHOT_LOOKBACK,
            skip_recent_days=_SNAPSHOT_SKIP,
            group_by_exchange=False,
        ),
        validated=ranking.meta.validated,
        g7_summary=None,
        carry_in=carry,
    )
    try:
        created = repo.create_round(rnd)
    except RoundConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("라운드 생성: label=%s as_of=%s top20=%d", body.label, anchor_as_of, len(snapshot))
    return _to_round_model(created, repo)


@router.get("/rounds", response_model=list[RoundListItem])
def list_rounds(repo: RoundRepository = Depends(get_round_repo)) -> list[RoundListItem]:
    return [
        RoundListItem(
            id=r.id or 0,
            label=r.label,
            status=r.status.value,
            opened_on=r.opened_on,
            closed_at=r.closed_at,
        )
        for r in repo.list_rounds()
    ]


@router.get("/rounds/{round_id}", response_model=RoundModel)
def get_round(round_id: int, repo: RoundRepository = Depends(get_round_repo)) -> RoundModel:
    rnd = repo.get_round(round_id)
    if rnd is None:
        raise HTTPException(status_code=404, detail=f"라운드 부재: id={round_id}")
    return _to_round_model(rnd, repo)


@router.patch("/rounds/{round_id}", response_model=RoundModel)
def set_top5(
    round_id: int,
    body: Top5Request,
    repo: RoundRepository = Depends(get_round_repo),
) -> RoundModel:
    """Top5 확정 + 토의 메모 — top5 ⊆ Top20 스냅샷 검증(스냅샷 밖 = 모델 앵커 미정의·422)."""
    rnd = _require_open(round_id, repo)
    snapshot_tickers = {e.ticker for e in rnd.top20_snapshot}
    outside = [t for t in body.top5 if t not in snapshot_tickers]
    if outside:
        raise HTTPException(
            status_code=422,
            detail=f"Top5 는 Top20 스냅샷 부분집합이어야 함 — 밖: {outside}",
        )
    updated = repo.set_top5(round_id, memo=body.memo, top5=body.top5)
    return _to_round_model(updated, repo)


# ── 거래·현금흐름·void ───────────────────────────────────────────────────────


@router.post("/rounds/{round_id}/trades", response_model=TradeModel)
def add_trade(
    round_id: int,
    body: TradeCreateRequest,
    repo: RoundRepository = Depends(get_round_repo),
) -> TradeModel:
    rnd = _require_open(round_id, repo)
    if not rnd.top5 and body.side == "BUY":
        raise HTTPException(
            status_code=422, detail="Top5 확정 전 매수 금지(규율 순서 — PATCH 로 확정 먼저)"
        )
    today = datetime.now(tz=UTC).date()
    if not (rnd.opened_on <= body.executed_on <= today):
        raise HTTPException(
            status_code=422,
            detail=f"체결일 범위 위반: {body.executed_on} ∉ [{rnd.opened_on}, {today}]",
        )
    stock_id = repo.stock_id_for(body.ticker)
    if stock_id is None:
        raise HTTPException(
            status_code=422, detail=f"종목 마스터에 없음: {body.ticker}(오타 확인)"
        )
    candidate = Trade(
        id=None,
        round_id=round_id,
        stock_id=stock_id,
        ticker=body.ticker,
        side=TradeSide(body.side),
        quantity=body.quantity,
        price=body.price,
        fee=body.fee,
        executed_on=body.executed_on,
        note=body.note,
    )
    trades = repo.list_trades()
    splits = repo.list_splits({t.ticker for t in trades} | {body.ticker})
    try:
        validate_new_trade(candidate, trades=trades, flows=repo.list_cash_flows(), splits=splits)
    except LedgerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    created = repo.insert_trade(candidate)
    return _to_trade_model(created)


@router.post("/rounds/{round_id}/cash-flows", response_model=CashFlowModel)
def add_cash_flow(
    round_id: int,
    body: CashFlowCreateRequest,
    repo: RoundRepository = Depends(get_round_repo),
) -> CashFlowModel:
    rnd = _require_open(round_id, repo)
    if body.amount == 0:
        raise HTTPException(status_code=422, detail="금액 0 금지(입금 +, 출금 −)")
    today = datetime.now(tz=UTC).date()
    if not (rnd.opened_on <= body.flowed_on <= today):
        raise HTTPException(
            status_code=422,
            detail=f"일자 범위 위반: {body.flowed_on} ∉ [{rnd.opened_on}, {today}]",
        )
    candidate = CashFlow(
        id=None, round_id=round_id, amount=body.amount, flowed_on=body.flowed_on, note=body.note
    )
    trades = repo.list_trades()
    flows = [*repo.list_cash_flows(), candidate]
    splits = repo.list_splits({t.ticker for t in trades})
    dates = [t.executed_on for t in trades] + [f.flowed_on for f in flows]
    try:
        replay_ledger(trades, flows, splits, grid=[max(dates)])
    except LedgerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    created = repo.insert_cash_flow(candidate)
    return _to_flow_model(created)


@router.post("/trades/{trade_id}/void", response_model=TradeModel)
def void_trade(
    trade_id: int,
    body: VoidRequest,
    repo: RoundRepository = Depends(get_round_repo),
) -> TradeModel:
    """soft-void 정정 — closed 라운드 거래는 409(동결 스냅샷 발산 차단·스펙 C-5)."""
    all_trades = repo.list_trades(include_voided=True)
    target = next((t for t in all_trades if t.id == trade_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"trade 부재: id={trade_id}")
    owner = repo.get_round(target.round_id)
    if owner is None or owner.status is not RoundStatus.OPEN:
        raise HTTPException(
            status_code=409, detail="closed 라운드 거래는 void 불가(동결 성과 발산 차단)"
        )
    live = repo.list_trades()
    splits = repo.list_splits({t.ticker for t in live})
    try:
        validate_void(trade_id, trades=live, flows=repo.list_cash_flows(), splits=splits)
    except LedgerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    voided = repo.void_trade(trade_id, reason=body.reason, at=datetime.now(tz=UTC))
    return _to_trade_model(voided)


# ── 성과·마감·벤치 동기화 ────────────────────────────────────────────────────


@router.get("/rounds/{round_id}/performance", response_model=PerformanceResponse)
def round_performance(
    round_id: int,
    base_dir: Path = Depends(get_base_dir),
    repo: RoundRepository = Depends(get_round_repo),
) -> PerformanceResponse:
    rnd = repo.get_round(round_id)
    if rnd is None:
        raise HTTPException(status_code=404, detail=f"라운드 부재: id={round_id}")
    perf = _compute_performance(rnd, base_dir, repo)
    return _to_performance_response(perf, validated=rnd.validated)


@router.post("/rounds/{round_id}/close", response_model=RoundModel)
def close_round(
    round_id: int,
    body: RetrospectiveModel,
    base_dir: Path = Depends(get_base_dir),
    repo: RoundRepository = Depends(get_round_repo),
) -> RoundModel:
    """마감 — 신선도 게이트(stale→409 수집 먼저)·구조화 회고 필수·성과 스냅샷 동결(vintage 포함)."""
    rnd = _require_open(round_id, repo)
    perf = _compute_performance(rnd, base_dir, repo)
    if perf.stale:
        raise HTTPException(
            status_code=409,
            detail=f"가격 기준일 stale(as_of={perf.as_of}) — 수집(/api/ingest) 후 마감",
        )
    closed_at = datetime.now(tz=UTC)
    snapshot: dict[str, object] = {
        # 동결값 + 계산 입력 메타(vintage) — '마감 후 불변'을 재현 가능하게(스펙 §3.4).
        "as_of": perf.as_of.isoformat(),
        "return_convention": "price",
        "actual_twr": str(perf.actual.cumulative_return),
        "top5_twr": str(perf.top5_model.cumulative_return),
        "top20_twr": str(perf.top20_model.cumulative_return),
        "spy_twr": str(perf.spy.cumulative_return),
        "selection_effect": perf.selection_effect,
        "execution_effect": perf.execution_effect,
        "hit_rate": perf.hit_rate,
        "n_picks_cumulative": perf.n_picks_cumulative,
        "verdict_deferred": perf.verdict_deferred,
        "liquidated": list(perf.liquidated),
        "computed_at": closed_at.isoformat(),
    }
    retro = RoundRetrospective(
        judgment_good=body.judgment_good,
        judgment_bad=body.judgment_bad,
        rule_change=body.rule_change,
    )
    closed = repo.close_round(
        round_id, retrospective=retro, performance_snapshot=snapshot, closed_at=closed_at
    )
    logger.info("라운드 마감: id=%d as_of=%s", round_id, perf.as_of)
    return _to_round_model(closed, repo)


@router.post("/benchmark/sync", response_model=BenchmarkSyncResponse)
def benchmark_sync(
    base_dir: Path = Depends(get_base_dir),
    source: DataSource = Depends(get_source),
    repo: RoundRepository = Depends(get_round_repo),
) -> BenchmarkSyncResponse:
    """SPY 가격(격리 서브트리) + 관련 티커 분할 이벤트 수집 — 성과 계산 선행 단계.

    분할 수집 대상 = 활성 라운드의 top20∪top5∪거래 티커 + SPY(소량·per-symbol).
    fetch_splits 는 EodhdSource 전용(캡처 명세) — 다른 소스면 가격만 동기화(명시 로그).
    """
    rnd = repo.get_open_round()
    start = rnd.anchor_as_of if rnd is not None else None
    price_rows = sync_benchmark_prices(base_dir, source, start=start)

    split_events = 0
    from ...data.eodhd import EodhdSource

    if isinstance(source, EodhdSource) and rnd is not None:
        tickers = (
            {e.ticker for e in rnd.top20_snapshot}
            | set(rnd.top5)
            | {t.ticker for t in repo.list_trades()}
            | {BENCHMARK_TICKER}
        )
        now = datetime.now(tz=UTC)
        events: list[SplitEvent] = []
        for ticker in sorted(tickers):
            for effective_on, ratio in source.fetch_splits(ticker, start=rnd.anchor_as_of):
                events.append(
                    SplitEvent(
                        ticker=ticker,
                        effective_on=effective_on,
                        ratio=ratio,
                        source=source.name,
                        ingested_at=now,
                    )
                )
        split_events = repo.upsert_splits(events)
    elif rnd is None:
        logger.info("benchmark/sync: 활성 라운드 없음 — SPY 가격만 동기화")
    else:
        logger.warning("benchmark/sync: EODHD 아닌 소스 — 분할 수집 생략(가격만)")
    return BenchmarkSyncResponse(price_rows=price_rows, split_events=split_events)


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────


def _require_open(round_id: int, repo: RoundRepository) -> PortfolioRound:
    rnd = repo.get_round(round_id)
    if rnd is None:
        raise HTTPException(status_code=404, detail=f"라운드 부재: id={round_id}")
    if rnd.status is not RoundStatus.OPEN:
        raise HTTPException(status_code=409, detail=f"closed 라운드 — 변경 불가: id={round_id}")
    return rnd


def _compute_performance(
    rnd: PortfolioRound, base_dir: Path, repo: RoundRepository
) -> RoundPerformance:
    trades = [t for t in repo.list_trades() if t.round_id == rnd.id]
    flows = [f for f in repo.list_cash_flows() if f.round_id == rnd.id]
    tickers = {e.ticker for e in rnd.top20_snapshot} | set(rnd.top5) | {t.ticker for t in trades}
    today = datetime.now(tz=UTC).date()
    closes = load_raw_close_range(
        base_dir, tickers=tickers, start=rnd.anchor_as_of, end=today
    )
    spy_closes = load_raw_close_range(
        base_dir / BENCHMARK_SUBDIR,
        tickers={BENCHMARK_TICKER},
        start=rnd.anchor_as_of,
        end=today,
    ).get(BENCHMARK_TICKER, [])
    splits = repo.list_splits(tickers | {BENCHMARK_TICKER})
    n_prior = sum(
        len(r.top5) for r in repo.list_rounds() if r.status is RoundStatus.CLOSED and r.id != rnd.id
    )
    try:
        return compute_round_performance(
            rnd,
            trades=trades,
            flows=flows,
            splits=splits,
            closes=closes,
            spy_closes=spy_closes,
            spy_splits=list(splits.get(BENCHMARK_TICKER, ())),
            delisted=repo.delisted_tickers(tickers),
            today=today,
            n_picks_prior=n_prior,
        )
    except PerformanceUnmeasurableError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"측정불가: {exc} — 벤치 동기화(/api/tracking… POST /benchmark/sync) 선행",
        ) from exc
    except LedgerError as exc:
        raise HTTPException(status_code=422, detail=f"원장 불변식 위반: {exc}") from exc


def _to_series_model(perf: SeriesPerf) -> SeriesPerfModel:
    return SeriesPerfModel(
        cumulative_return=float(perf.cumulative_return),
        max_drawdown=perf.max_drawdown,
        index=[PerfPoint(day=d, value=float(v)) for d, v in perf.index],
        unmeasurable=list(perf.unmeasurable),
    )


def _to_performance_response(perf: RoundPerformance, *, validated: bool) -> PerformanceResponse:
    return PerformanceResponse(
        as_of=perf.as_of,
        stale=perf.stale,
        return_convention="price",
        actual=_to_series_model(perf.actual),
        top5_model=_to_series_model(perf.top5_model),
        top20_model=_to_series_model(perf.top20_model),
        spy=_to_series_model(perf.spy),
        selection_effect=perf.selection_effect,
        execution_effect=perf.execution_effect,
        contributions=[
            ContributionModel(ticker=c.ticker, pnl=float(c.pnl)) for c in perf.contributions
        ],
        slippages=[
            SlippageModel(
                trade_id=s.trade_id,
                ticker=s.ticker,
                side=s.side,
                exec_price=float(s.exec_price),
                day_close=None if s.day_close is None else float(s.day_close),
                cost_pct=s.cost_pct,
            )
            for s in perf.slippages
        ],
        hit_rate=perf.hit_rate,
        n_picks_cumulative=perf.n_picks_cumulative,
        verdict_deferred=perf.verdict_deferred,
        liquidated=list(perf.liquidated),
        validated=validated,
        warning=_warning(validated),
    )


def _to_trade_model(trade: Trade) -> TradeModel:
    return TradeModel(
        id=trade.id or 0,
        round_id=trade.round_id,
        ticker=trade.ticker,
        side=trade.side.value,
        quantity=float(trade.quantity),
        price=float(trade.price),
        fee=float(trade.fee),
        executed_on=trade.executed_on,
        note=trade.note,
        voided_at=trade.voided_at,
        void_reason=trade.void_reason,
    )


def _to_flow_model(flow: CashFlow) -> CashFlowModel:
    return CashFlowModel(
        id=flow.id or 0,
        round_id=flow.round_id,
        amount=float(flow.amount),
        flowed_on=flow.flowed_on,
        note=flow.note,
        voided_at=flow.voided_at,
    )


def _to_round_model(rnd: PortfolioRound, repo: RoundRepository) -> RoundModel:
    rid = rnd.id or 0
    trades = [
        _to_trade_model(t) for t in repo.list_trades(include_voided=True) if t.round_id == rid
    ]
    flows = [
        _to_flow_model(f)
        for f in repo.list_cash_flows(include_voided=True)
        if f.round_id == rid
    ]
    return RoundModel(
        id=rid,
        label=rnd.label,
        status=rnd.status.value,
        opened_on=rnd.opened_on,
        anchor_as_of=rnd.anchor_as_of,
        rule_signature=rnd.rule_signature,
        validated=rnd.validated,
        warning=_warning(rnd.validated),
        top20=[
            SnapshotEntryModel(
                cik=e.cik,
                ticker=e.ticker,
                exchange=e.exchange,
                rank=e.rank,
                score=e.score,
                factors=dict(e.factors),
                anchor_close=None if e.anchor_close is None else float(e.anchor_close),
            )
            for e in rnd.top20_snapshot
        ],
        carry_in=[
            CarryInModel(
                ticker=c.ticker,
                quantity=float(c.quantity),
                anchor_close=None if c.anchor_close is None else float(c.anchor_close),
            )
            for c in rnd.carry_in
        ],
        discussion_memo=rnd.discussion_memo,
        top5=list(rnd.top5),
        retrospective=None
        if rnd.retrospective is None
        else RetrospectiveModel(
            judgment_good=rnd.retrospective.judgment_good,
            judgment_bad=rnd.retrospective.judgment_bad,
            rule_change=rnd.retrospective.rule_change,
        ),
        closed_at=rnd.closed_at,
        trades=trades,
        cash_flows=flows,
    )
