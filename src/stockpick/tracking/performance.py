"""성과 계산 — 분할 정규화·공통 as-of·일별 chain-linked TWR·모델 계열(스펙 §3.1~3.3).

**전 계열 price return(v1 통일·배당 미반영 명시)**: raw close + SPLIT 정규화만. adj_factor
(분할+배당 혼합)는 여기서 사용 금지. **TWR 규약**: `r_d = V_d / (V_{d-1} + F_d) − 1`,
F=외부 현금흐름(start-of-day)·BUY/SELL 은 내부 이체(F 불포함) — 중간 입출금이 수익률을
오염시키지 않는다(단순수익률 붕괴 해소). 분모 0(미펀딩) → r=0.

Decimal/float 경계(backtest/metrics.py 관례·import 는 안 함 — 모듈 경계): 돈·평가·지수·누적
수익 = Decimal, MDD·비율 통계 = float 1곳 격리. 순수 함수(I/O 없음) — 가격은 상위(API)가
`data/price_read` 로 로드해 주입.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date

    from .ledger import LedgerDay
    from .types import CashFlow, PortfolioRound, SplitEvent, Trade


@dataclass(frozen=True, slots=True)
class SeriesPerf:
    """한 계열의 TWR 결과 — 지수(앵커=1)·누적수익(Decimal)·MDD(float 격리)·측정불가 종목."""

    index: tuple[tuple[date, Decimal], ...]
    cumulative_return: Decimal
    max_drawdown: float
    unmeasurable: tuple[str, ...] = ()


def normalize_splits(
    closes: Sequence[tuple[date, Decimal]],
    splits: Sequence[SplitEvent],
) -> list[tuple[date, Decimal]]:
    """raw close → 분할 정규화 계열: N_t = raw_t × Π{ratio : effective_on ≤ t}.

    acceptance 실측: effective_on = 분할 후 첫 거래일(당일 가격 이미 분할 반영) → 당일부터
    ratio 적용이 연속 계열을 만든다(2:1 전 100·후 50 → N 연속 100). 배당은 건드리지 않음
    (price return — 스펙 §3.1).
    """
    if not splits:
        return list(closes)
    events = sorted(splits, key=lambda ev: ev.effective_on)
    out: list[tuple[date, Decimal]] = []
    for day, close in closes:
        factor = Decimal(1)
        for ev in events:
            if ev.effective_on <= day:
                factor *= ev.ratio
            else:
                break
        out.append((day, close * factor))
    return out


def resolve_as_of(
    max_dates: Mapping[str, date],
    *,
    required: set[str],
    inactive: set[str],
) -> date | None:
    """공통 as-of = **활성** 종목만 min(max(trade_date)) — 계열 간 시점 불일치 노이즈 차단.

    폐지·영구결측(inactive)은 제외 — 포함하면 한 종목 폐지가 전체 측정을 폐지일로 절단
    (폐지 청산 규약과 충돌·C-3). 활성 종목 데이터가 하나도 없으면 None(측정불가·조용한 0 금지).
    """
    active_dates = [
        max_dates[t] for t in sorted(required - inactive) if t in max_dates
    ]
    if not active_dates:
        return None
    return min(active_dates)


def _mdd(index: Sequence[tuple[date, Decimal]]) -> float:
    """지수 계열 최대낙폭(peak-to-trough) — float 1곳 격리(metrics 관례)."""
    peak = Decimal(0)
    worst = Decimal(0)
    for _, value in index:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return float(worst)


def _chain(values: Sequence[tuple[date, Decimal, Decimal]]) -> tuple[tuple[date, Decimal], ...]:
    """(day, V_d, F_d) → chain-linked TWR 지수. r_d = V/(V_prev+F) − 1, 분모 0 → r=0."""
    index: list[tuple[date, Decimal]] = []
    level = Decimal(1)
    prev_value: Decimal | None = None
    for day, value, flow in values:
        if prev_value is None:
            # 첫 grid 날: 기준점 — 당일 유입 후 가치가 앵커(r=0·지수 1).
            index.append((day, level))
            prev_value = value
            continue
        denom = prev_value + flow
        r = Decimal(0) if denom == 0 else value / denom - 1
        level *= Decimal(1) + r
        index.append((day, level))
        prev_value = value
    return tuple(index)


def actual_series(
    ledger: Sequence[LedgerDay],
    closes: Mapping[str, Mapping[date, Decimal]],
    *,
    liquidations: Mapping[str, tuple[date, Decimal]],
) -> SeriesPerf:
    """계열 ① 실보유 — 원장(수량·현금) × raw close 일별 평가 → TWR.

    결측일 = 직전가 carry-forward(일시 정지). liquidations[t]=(청산일, 마지막 유효가): 청산일
    이후 그 종목 평가는 마지막 유효가 고정 — 폐지 시 현금 전환은 원장이 아니라 평가 동결로
    표현(재분배 금지·스펙 §3.3). 평가 불능(가격 이력 전무) 종목은 unmeasurable 보고 + 평가 0
    제외(조용한 0 아님 — 명시 보고).
    """
    last_close: dict[str, Decimal] = {}
    unmeasurable: set[str] = set()
    rows: list[tuple[date, Decimal, Decimal]] = []
    for day_state in ledger:
        total = day_state.cash
        for ticker, qty in day_state.positions.items():
            liq = liquidations.get(ticker)
            price: Decimal | None
            if liq is not None and day_state.day >= liq[0]:
                price = liq[1]  # 폐지 — 마지막 유효가 동결
            else:
                price = closes.get(ticker, {}).get(day_state.day)
                if price is None:
                    price = last_close.get(ticker)  # 일시 결측 carry-forward
                else:
                    last_close[ticker] = price
            if price is None:
                unmeasurable.add(ticker)
                continue
            total += qty * price
        rows.append((day_state.day, total, day_state.external_flow))
    index = _chain(rows)
    cumulative = index[-1][1] - 1 if index else Decimal(0)
    return SeriesPerf(
        index=index,
        cumulative_return=cumulative,
        max_drawdown=_mdd(index),
        unmeasurable=tuple(sorted(unmeasurable)),
    )


def model_series(
    tickers: Sequence[str],
    *,
    anchor: date,
    closes_norm: Mapping[str, Mapping[date, Decimal]],
    grid: Sequence[date],
    frozen: Mapping[str, date],
) -> SeriesPerf:
    """계열 ②③④ 공통 — 등가중 buy-and-hold 모델(앵커 고정 가중·리밸 없음·드리프트).

    index_d = (1/N) Σ_i G_i(d), G_i(d) = N_i(min(d, frozen_i)) / N_i(anchor). frozen[t]=폐지
    동결일(마지막 유효가로 청산 후 지수 동결 — 잔여 재분배 금지 = 루프 내 생존편향 차단).
    앵커 가격 없는 종목 = 배제 + unmeasurable 보고. 외부 흐름 없음 → TWR = 지수 그 자체.
    SPY(계열 ④)는 1종목 특수화. 결측일 carry-forward.
    """
    anchors: dict[str, Decimal] = {}
    unmeasurable: list[str] = []
    for ticker in tickers:
        base = closes_norm.get(ticker, {}).get(anchor)
        if base is None or base <= 0:
            unmeasurable.append(ticker)
        else:
            anchors[ticker] = base
    if not anchors:
        return SeriesPerf(
            index=(), cumulative_return=Decimal(0), max_drawdown=0.0,
            unmeasurable=tuple(unmeasurable),
        )

    last_price: dict[str, Decimal] = dict(anchors)
    index: list[tuple[date, Decimal]] = []
    n = Decimal(len(anchors))
    for day in grid:
        total_g = Decimal(0)
        for ticker, base in anchors.items():
            freeze_day = frozen.get(ticker)
            eval_day = day if freeze_day is None or day <= freeze_day else freeze_day
            price = closes_norm.get(ticker, {}).get(eval_day)
            if price is None:
                price = last_price[ticker]  # 결측 carry-forward(동결 포함)
            else:
                last_price[ticker] = price
            total_g += price / base
        index.append((day, total_g / n))
    cumulative = index[-1][1] - 1 if index else Decimal(0)
    return SeriesPerf(
        index=tuple(index),
        cumulative_return=cumulative,
        max_drawdown=_mdd(index),
        unmeasurable=tuple(unmeasurable),
    )


# ── 라운드 성과 오케스트레이션(스펙 §3.2 — 4계열+파생+보조지표) ────────────────

_STALE_CALENDAR_DAYS = 7  # ≈5거래일(달력 근사) — 초과 시 stale 배지(close 게이트는 API 책임)
_VERDICT_MIN_PICKS = 20  # 누적 pick N<20 동안 "판정 유보" 라벨 고정(소표본 노이즈 오독 차단)


@dataclass(frozen=True, slots=True)
class Contribution:
    """종목별 달러 P&L 기여(회고 1차 재료) — 평가 기반(평단 규약 불요·스펙 C-4)."""

    ticker: str
    pnl: Decimal  # MV_end + Σ(SELL 현금) − Σ(BUY 현금·fee 포함) − MV_carryin


@dataclass(frozen=True, slots=True)
class Slippage:
    """거래별 체결 슬리피지 — 체결가 vs 당일 종가(양수=불리). 당일 봉 결측=None(사유 보존)."""

    trade_id: int | None
    ticker: str
    side: str
    exec_price: Decimal
    day_close: Decimal | None
    cost_pct: float | None


@dataclass(frozen=True, slots=True)
class RoundPerformance:
    """라운드 성과 종합 — 전 계열 price return(배당 미반영)·공통 as-of 절단."""

    as_of: date
    grid: tuple[date, ...]
    stale: bool
    actual: SeriesPerf
    top5_model: SeriesPerf
    top20_model: SeriesPerf
    spy: SeriesPerf
    selection_effect: float  # top5 − top20 (수동 압축의 부가가치)
    execution_effect: float  # actual − top5 (체결 타이밍·슬리피지·현금드래그)
    contributions: tuple[Contribution, ...]
    slippages: tuple[Slippage, ...]
    hit_rate: float | None  # top5 중 모델수익>0 비율(측정가능분·없으면 None)
    n_picks_cumulative: int
    verdict_deferred: bool  # N<20 — 라운드당 판정은 통계적으로 무의미(고정 라벨)
    liquidated: tuple[str, ...]  # 폐지 청산 처리된 종목(마지막 유효가 동결)


class PerformanceUnmeasurableError(Exception):
    """공통 as-of 산출 불가(활성 종목 가격 전무) — 측정불가 명시 실패(조용한 0 금지)."""


def _to_date_map(closes: Sequence[tuple[date, Decimal]]) -> dict[date, Decimal]:
    return dict(closes)


def _price_on_or_before(closes: Mapping[date, Decimal], day: date) -> Decimal | None:
    """day 이하 가장 최근 종가(carry-forward) — 없으면 None(명시)."""
    best: tuple[date, Decimal] | None = None
    for d, price in closes.items():
        if d <= day and (best is None or d > best[0]):
            best = (d, price)
    return None if best is None else best[1]


def compute_round_performance(
    rnd: PortfolioRound,
    *,
    trades: Sequence[Trade],
    flows: Sequence[CashFlow],
    splits: Mapping[str, Sequence[SplitEvent]],
    closes: Mapping[str, Sequence[tuple[date, Decimal]]],
    spy_closes: Sequence[tuple[date, Decimal]],
    spy_splits: Sequence[SplitEvent],
    delisted: set[str],
    today: date,
    n_picks_prior: int,
    stale_after_days: int = _STALE_CALENDAR_DAYS,
) -> RoundPerformance:
    """4계열(실보유·Top5모델·Top20모델·SPY)+파생 2+보조지표 — 순수 계산(가격은 주입).

    공통 as-of = 활성 종목 min(max date)(SPY 포함) — 계열 간 시점 불일치 노이즈 차단.
    폐지(delisted)는 마지막 유효가 청산·동결(재분배 금지). 그리드 = SPY 거래일(NYSE 프록시).
    v1 한계 명시: 정지 감지(5거래일 무데이터) 미구현 — 정지 종목 stale 데이터가 as-of 를
    끌어내릴 수 있음(공통 절단이라 왜곡은 아님·느려질 뿐).
    """
    top20 = [e.ticker for e in rnd.top20_snapshot]
    traded = {t.ticker for t in trades}
    required = set(top20) | set(rnd.top5) | traded

    close_maps: dict[str, dict[date, Decimal]] = {
        t: _to_date_map(series) for t, series in closes.items()
    }
    spy_map = _to_date_map(spy_closes)
    max_dates = {t: max(m) for t, m in close_maps.items() if m}
    if spy_map:
        max_dates["SPY"] = max(spy_map)

    as_of = resolve_as_of(max_dates, required=required | {"SPY"}, inactive=delisted)
    if as_of is None:
        msg = "공통 as-of 산출 불가 — 활성 종목·SPY 가격 데이터 전무(수집 선행 필요)"
        raise PerformanceUnmeasurableError(msg)

    grid = tuple(sorted(d for d in spy_map if rnd.anchor_as_of <= d <= as_of))
    if not grid:
        msg = f"SPY 그리드 비어 있음: window=[{rnd.anchor_as_of}..{as_of}] — 벤치 수집 선행"
        raise PerformanceUnmeasurableError(msg)

    # 분할 정규화(모델 계열용) — raw 는 실보유 평가·슬리피지용으로 유지.
    norm_maps: dict[str, dict[date, Decimal]] = {
        t: _to_date_map(normalize_splits(list(series), list(splits.get(t, ()))))
        for t, series in closes.items()
    }
    spy_norm = _to_date_map(normalize_splits(list(spy_closes), list(spy_splits)))

    # 폐지 처리 — 마지막 유효 (일자, 가격) 동결.
    liquidations: dict[str, tuple[date, Decimal]] = {}
    frozen: dict[str, date] = {}
    for t in sorted(delisted & (required | set(close_maps))):
        m = close_maps.get(t)
        if m:
            last_day = max(m)
            liquidations[t] = (last_day, m[last_day])
            frozen[t] = last_day

    from .ledger import replay_ledger

    ledger = replay_ledger(trades, flows, splits, grid=list(grid))
    actual = actual_series(ledger, close_maps, liquidations=liquidations)
    top5_model = model_series(
        list(rnd.top5), anchor=rnd.anchor_as_of, closes_norm=norm_maps, grid=grid, frozen=frozen
    )
    top20_model = model_series(
        top20, anchor=rnd.anchor_as_of, closes_norm=norm_maps, grid=grid, frozen=frozen
    )
    spy = model_series(
        ["SPY"], anchor=rnd.anchor_as_of, closes_norm={"SPY": spy_norm}, grid=grid, frozen={}
    )

    # 기여도 — 평가 기반 달러 P&L(라운드 창): MV_end + SELL현금 − BUY현금 − MV_carryin.
    carry_qty = {c.ticker: c.quantity for c in rnd.carry_in}
    carry_px = {c.ticker: c.anchor_close for c in rnd.carry_in}
    end_positions = ledger[-1].positions if ledger else {}
    contributions: list[Contribution] = []
    for t in sorted(traded | set(carry_qty)):
        end_qty = end_positions.get(t, Decimal(0))
        liq = liquidations.get(t)
        end_px = (
            liq[1] if liq is not None and as_of >= liq[0]
            else _price_on_or_before(close_maps.get(t, {}), as_of)
        )
        mv_end = end_qty * end_px if end_px is not None else Decimal(0)
        buys = sum(
            (
                tr.quantity * tr.price + tr.fee
                for tr in trades
                if tr.ticker == t and tr.side.value == "BUY"
            ),
            Decimal(0),
        )
        sells = sum(
            (
                tr.quantity * tr.price - tr.fee
                for tr in trades
                if tr.ticker == t and tr.side.value == "SELL"
            ),
            Decimal(0),
        )
        anchor_px = carry_px.get(t)
        mv_carry = (
            carry_qty.get(t, Decimal(0)) * anchor_px if anchor_px is not None else Decimal(0)
        )
        contributions.append(Contribution(ticker=t, pnl=mv_end + sells - buys - mv_carry))

    # 슬리피지 — 체결가 vs 당일 종가(raw·양수=불리). 당일 봉 결측=None.
    slippages: list[Slippage] = []
    for tr in trades:
        day_close = close_maps.get(tr.ticker, {}).get(tr.executed_on)
        cost: float | None = None
        if day_close is not None and day_close > 0:
            diff = (
                (tr.price - day_close) if tr.side.value == "BUY" else (day_close - tr.price)
            )
            cost = float(diff / day_close)
        slippages.append(
            Slippage(
                trade_id=tr.id,
                ticker=tr.ticker,
                side=tr.side.value,
                exec_price=tr.price,
                day_close=day_close,
                cost_pct=cost,
            )
        )

    # 히트레이트 — top5 중 모델 수익(정규화·anchor→as_of)>0 비율(측정가능분만).
    hits = total = 0
    for t in rnd.top5:
        base = norm_maps.get(t, {}).get(rnd.anchor_as_of)
        cur = _price_on_or_before(norm_maps.get(t, {}), as_of)
        if base is None or base <= 0 or cur is None:
            continue
        total += 1
        if cur > base:
            hits += 1
    hit_rate = None if total == 0 else hits / total

    n_cum = n_picks_prior + len(rnd.top5)
    return RoundPerformance(
        as_of=as_of,
        grid=grid,
        stale=(today - as_of).days > stale_after_days,
        actual=actual,
        top5_model=top5_model,
        top20_model=top20_model,
        spy=spy,
        selection_effect=float(top5_model.cumulative_return - top20_model.cumulative_return),
        execution_effect=float(actual.cumulative_return - top5_model.cumulative_return),
        contributions=tuple(contributions),
        slippages=tuple(slippages),
        hit_rate=hit_rate,
        n_picks_cumulative=n_cum,
        verdict_deferred=n_cum < _VERDICT_MIN_PICKS,
        liquidated=tuple(sorted(liquidations)),
    )
