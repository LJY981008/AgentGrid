"""백테스트 엔진 — 단일 config 러너. rolling as_of 리밸런싱·forward-return·폐지청산·비용.

룩어헤드 BLOCKING: 랭킹은 ports.load(as_of=t)(<=t), 진입은 t **다음** 거래일(동시성 누설 차단).
생존편향 BLOCKING: 후보는 UniversePort.constituents(as_of=t) 교집합(가격파일 존재 아님). 보유 중
폐지(delisting_event)면 delisting_recovery_rate 로 청산(gap≠폐지 — 명시 이벤트로만).
식별자: IdentityResolver 로 ticker→cik 앵커 enrich(가능 시).
키 = cik or ticker(strategy._key 와 동일 규칙).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from ..rules.factors import momentum_universe
from ..rules.ranking import rank_by_momentum
from . import calendar, costs
from .metrics import compute_metrics

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from ..rules._scan import PricePoint
    from ..types import Exchange, TopEntry
    from .config import BacktestConfig
    from .metrics import BacktestResult
    from .ports import IdentityResolver, PriceSeriesPort, UniversePort
    from .strategy import Strategy

logger = logging.getLogger(__name__)

_PERIODS_PER_YEAR = {"monthly": 12, "quarterly": 4}
_CAVEAT_GOLGYEOK = (
    "골격: cik 미해소 가능·합성/제한 폐지·데이터 구간 짧음 — 결과 미검증(S6 게이트 전 알파 아님)"
)


def run(
    config: BacktestConfig,
    *,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    strategy: Strategy,
) -> BacktestResult:
    """리밸 루프 → 자산곡선 → BacktestResult. 데이터량 무관(같은 코드, 더 많은 데이터)."""
    exchanges = price_port.ticker_exchanges()
    plan = calendar.holding_periods(
        price_port.trading_days(),
        start=config.start,
        end=config.end,
        freq=config.rebalance_freq,
    )

    equity = Decimal(1)
    curve: list[tuple[date, Decimal]] = []
    period_returns: list[Decimal] = []
    turnover_total = Decimal(0)
    cost_total = Decimal(0)
    n_delisted = 0
    n_skipped = 0
    prev_weights: dict[str, Decimal] = {}

    # 초기 자본 앵커 — MDD 가 첫 기간 낙폭을 포착하고 total_return 기준점이 1.0 이 되도록.
    if plan.anchor is not None:
        curve.append((plan.anchor, equity))

    for t, entry_day, exit_day in plan.periods:
        ranked = _rank_at(config, price_port, universe_port, identity, exchanges, t)
        weights = strategy.weights(ranked, as_of=t)
        key_to_ticker = {(e.cik or e.ticker): e.ticker for e in ranked}

        # 비용: 회전(turnover)분에만. 진입 전 차감(equity_before 기준).
        turnover = _turnover(prev_weights, weights)
        cost_frac = costs.apply_cost_fraction(turnover, config.cost_bps)
        cost_amount = equity * cost_frac
        equity -= cost_amount
        turnover_total += turnover
        cost_total += cost_amount

        # 보유수익([entry,exit]·폐지청산). load_range 보유종목 × 구간만(full 전체 OOM 회피).
        # 정상 종목 equity/지표 불변. ⚠️ 보유기간 봉 0(첫봉>exit): full=미래봉(ret=0·룩어헤드)·
        # load_range=skip — equity 동일·NEW 가 룩어헤드 교정(critic C1·LOW3).
        held = price_port.load_range(
            tickers=set(key_to_ticker.values()), start=entry_day, end=exit_day
        )
        pret, delisted, skipped = _holding_period_return(
            weights,
            key_to_ticker,
            held,
            entry_day,
            exit_day,
            universe_port,
            config.delisting_recovery_rate,
        )
        n_delisted += delisted
        n_skipped += skipped
        equity *= Decimal(1) + pret
        period_returns.append(pret)
        curve.append((exit_day, equity))
        prev_weights = weights

    caveats = [_CAVEAT_GOLGYEOK]
    if n_skipped:
        # 조용한 결측 금지 — 진입가 결측 skip(암묵 현금화)을 명시 보고(데이터 공백 신호).
        logger.warning("진입가 결측으로 %d건 비중 skip(암묵 현금화) — 데이터 공백 확인", n_skipped)
        caveats.append(f"진입가 결측 {n_skipped}건 skip(암묵 현금화) — 데이터 공백 확인")

    # n_rebalances: 앵커 시드(1점)는 리밸 횟수에서 제외 — 실제 보유 기간 수.
    n_periods = len(period_returns)
    logger.info(
        "백테스트 완료: 리밸=%d, 보유기간=%d, 폐지청산=%d, skip=%d, 총회전=%s, 최종equity=%s",
        len(plan.periods),
        n_periods,
        n_delisted,
        n_skipped,
        turnover_total,
        equity,
    )
    return compute_metrics(
        curve,
        period_returns,
        periods_per_year=_PERIODS_PER_YEAR[config.rebalance_freq],
        turnover_total=turnover_total,
        cost_total=cost_total,
        n_rebalances=n_periods,
        n_delisted=n_delisted,
        benchmark_returns={},
        caveats=tuple(caveats),
        config_fingerprint=config.fingerprint(),
    )


def _rank_at(
    config: BacktestConfig,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    exchanges: Mapping[str, Exchange],
    t: date,
) -> list[TopEntry]:
    """as_of=t 랭킹. survivorship: constituents(as_of=t) 교집합(가격파일 존재 아님). cik enrich.

    load_range(tradable, [_window_start(t), t]) 로 거래가능 종목 × 랭킹 윈도우만 로드(load(as_of)
    전 종목 t 이하 전체 OOM 회피). 룩어헤드 상한 ≤t 유지·tradable 푸시필터. 결과 불변(momentum
    lookback+skip 거래일이 윈도우에 충분 포함). ⚠️ 장기 거래정지(윈도우에 봉 0)인 tradable 종목은
    스테일 모멘텀 없이 랭킹 제외 — full load(as_of) 대비 발산 가능(드묾·의도된 스테일 배제·benchmark
    members 와 동일 계열).
    """
    tradable = universe_port.constituents(as_of=t)
    series = price_port.load_range(tickers=tradable, start=_window_start(config, t), end=t)
    scores = momentum_universe(
        series,
        as_of=t,
        lookback_days=config.lookback_days,
        skip_recent_days=config.skip_recent_days,
    )
    # rank_by_momentum 은 점수난 ticker 전부 exchange 매핑을 요구 → series 의 거래소만 추림.
    ticker_to_exchange = {k: ex for k, ex in exchanges.items() if k in series}
    ranked = rank_by_momentum(
        scores,
        ticker_to_exchange,
        lookback_days=config.lookback_days,
        top_n=config.top_n,
        group_by_exchange=config.group_by_exchange,
    )
    # cik 앵커 enrich(가능 시) — 생존편향 ticker 재사용 오조인 방지. 미해소면 "" 유지(caveat).
    return [replace(e, cik=identity.cik_for(e.ticker, on=t) or e.cik) for e in ranked]


def _window_start(config: BacktestConfig, t: date) -> date:
    """랭킹 윈도우 하한 — momentum lookback+skip 거래일을 충분히 덮는 캘린더 여유(×2 + 30일).

    `load_range(tradable, start=_window_start(t), end=t)` 로 랭킹 입력을 좁혀 load(as_of) 전 종목
    t 이하 전체(OOM) 회피. 여유(거래일≈캘린더×5/7 → ×2 면 lookback+skip 거래일 확실 포함)가 momentum
    필요 구간을 덮어 결과 불변. 상장 초기 종목은 가용 전부(full load 와 동일 graceful).
    """
    span = (config.lookback_days + config.skip_recent_days) * 2 + 30
    return t - timedelta(days=span)


def _turnover(old: dict[str, Decimal], new: dict[str, Decimal]) -> Decimal:
    """편출+편입 절대비중 합(단방향 회전율). 전량 교체 시 ~2(매도1+매수1)."""
    keys = set(old) | set(new)
    return sum((abs(new.get(k, Decimal(0)) - old.get(k, Decimal(0))) for k in keys), Decimal(0))


def _holding_period_return(
    weights: dict[str, Decimal],
    key_to_ticker: dict[str, str],
    full: dict[str, list[PricePoint]],
    entry_day: date,
    exit_day: date,
    universe_port: UniversePort,
    recovery_rate: Decimal,
) -> tuple[Decimal, int, int]:
    """가중 보유수익 + (폐지청산 건수, 진입가 결측 skip 건수).

    폐지(entry<de<=exit)면 recovery_rate 청산.
    """
    total = Decimal(0)
    delisted = 0
    skipped = 0
    for key, w in weights.items():
        ticker = key_to_ticker.get(key, key)
        pts = full.get(ticker, [])
        entry_p = _price_on_or_after(pts, entry_day)
        if entry_p is None or entry_p <= 0:
            # 진입가 없음/비정상 — 조용한 추측 금지. 해당 비중 0기여(암묵 현금화) + skip 집계 보고.
            skipped += 1
            continue
        de = universe_port.delisting_event(ticker)
        if de is not None and entry_day < de <= exit_day:
            last_p = _price_before(pts, de) or entry_p
            ret = (last_p / entry_p) * recovery_rate - Decimal(1)
            delisted += 1
        else:
            exit_p = _price_on_or_before(pts, exit_day) or entry_p
            ret = exit_p / entry_p - Decimal(1)
        total += w * ret
    return total, delisted, skipped


def _price_on_or_after(pts: list[PricePoint], day: date) -> Decimal | None:
    for p in pts:
        if p.trade_date >= day:
            return p.adjusted
    return None


def _price_on_or_before(pts: list[PricePoint], day: date) -> Decimal | None:
    out: Decimal | None = None
    for p in pts:
        if p.trade_date <= day:
            out = p.adjusted
        else:
            break
    return out


def _price_before(pts: list[PricePoint], day: date) -> Decimal | None:
    out: Decimal | None = None
    for p in pts:
        if p.trade_date < day:
            out = p.adjusted
        else:
            break
    return out
