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

from ..rules.factors import financial_factors, momentum_universe
from ..rules.ranking import rank_by_momentum
from . import calendar, costs
from .metrics import compute_metrics
from .ports import MomentumScorePort, momentum_window_days
from .profile_types import timed

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from ..rules._scan import PricePoint
    from ..types import Exchange, FinancialFact, TopEntry
    from .config import BacktestConfig
    from .metrics import BacktestResult
    from .ports import IdentityResolver, LiquidityPort, PriceSeriesPort, UniversePort
    from .profile_types import PhaseTimer
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
    liquidity_port: LiquidityPort,
    financial_facts: list[FinancialFact] | None = None,
    profile: PhaseTimer | None = None,
) -> BacktestResult:
    """리밸 루프 → 자산곡선 → BacktestResult. 데이터량 무관(같은 코드, 더 많은 데이터).

    liquidity_port(ADR-010·필수): 매 리밸 거래가능 유니버스를 PIT 유동성 필터(close≥$5·ADV20≥$1M)
    로 좁힌다 — 벤치(equal_weight_universe)와 **대칭**(동일 as_of·동일 candidates 규약). 필터 끄려면
    FakeLiquidityPort(None)/_NoopLiquidityPort 명시 주입(조용한 skip 금지 — required 라 누락 불가).

    profile(선택) 주입 시 phase(rank/hold_load/hold_return)별 wall 을 누적 — **결과 불변**(계측만·
    관측용). 미주입(기본 None)이면 계측 0(stdlib `timed` 가 즉시 yield). 모듈경계: prometheus 무관.
    """
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
        if profile is not None:
            profile.tick_rebalance()  # 라이브 진행 곡선(계측만·결과 무관)
        with timed(profile, "rank"):
            ranked = _rank_at(
                config, price_port, universe_port, identity, exchanges, t, liquidity_port,
                financial_facts=financial_facts,
            )
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
        with timed(profile, "hold_load"):
            held = price_port.load_range(
                tickers=set(key_to_ticker.values()), start=entry_day, end=exit_day
            )
        with timed(profile, "hold_return"):
            pret, delisted, skipped = _holding_period_return(
                weights,
                key_to_ticker,
                held,
                entry_day,
                exit_day,
                universe_port,
                config.delisting_recovery_rate,
                config.period_return_cap,
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
        phase_profile=profile.snapshot() if profile is not None else None,
    )


def filter_by_roe(
    candidates: set[str],
    *,
    identity: IdentityResolver,
    financial_facts: list[FinancialFact],
    as_of: date,
    min_roe: Decimal,
    max_age_days: int | None,
) -> set[str]:
    """후보 ticker 중 **ROE>min_roe(흑자·PIT)** 인 것만 (B·방식 C·ROE→momentum 순서·H7).

    ticker→cik 해소(다중매칭=배제+카운트·raise 아님·H — 게이트 crash 방지) → financial_factors ROE
    (동일 FY·filed≤t·recency≤max_age) → ROE 산출가능 ∧ >min_roe 인 cik 의 ticker 만. 미해소 cik·무
    ROE=배제(결측 명시 배제·중립채움 금지). 룩어헤드/생존편향은 financial_factors·identity 가 보장.
    ⚠️ engine `_rank_at` 과 benchmark `equal_weight_universe` 가 **공유**(H3 대칭).
    """
    cik_of: dict[str, str] = {}
    dropped_multi = 0
    for ticker in candidates:
        try:
            cik = identity.cik_for(ticker, on=as_of)
        except ValueError:  # ticker_history 다중매칭 = 모호한 식별 → 배제(게이트 crash 방지)
            dropped_multi += 1
            continue
        if cik:
            cik_of[ticker] = cik
    if dropped_multi:
        logger.warning("ROE 필터 다중매칭 배제: %d종목(as_of=%s)", dropped_multi, as_of)
    scores = financial_factors(
        financial_facts, ciks=set(cik_of.values()), as_of=as_of, max_age_days=max_age_days
    )
    survivors: set[str] = set()
    for ticker, cik in cik_of.items():
        roe = scores[cik].roe
        if roe is not None and roe > min_roe:
            survivors.add(ticker)
    return survivors


def _rank_at(
    config: BacktestConfig,
    price_port: PriceSeriesPort,
    universe_port: UniversePort,
    identity: IdentityResolver,
    exchanges: Mapping[str, Exchange],
    t: date,
    liquidity_port: LiquidityPort,
    financial_facts: list[FinancialFact] | None = None,
) -> list[TopEntry]:
    """as_of=t 랭킹. survivorship: constituents(as_of=t) 교집합(가격파일 존재 아님). cik enrich.

    유동성(ADR-010): `tradable &= liquidity_port.liquid_tickers(t, tradable)` 로 PIT 유동 종목만
    랭킹 후보(벤치와 대칭·룩어헤드 ≤t). microcap penny·비유동 분모붕괴 배제(2차 폭발 해소).

    포트크기: `config.portfolio_pct` 설정 시 **decile 모드** — rank 절단 없이(top_n=후보수) 전
    후보를 전략(TopDecileEqualWeight)에 넘겨 상위 pct 선택. None 이면 고정 `config.top_n` 절단.
    decile 분모 = 유동 필터 통과 후 momentum 산출 후보 수(M1·전체 유니버스 아님).

    load_range(tradable, [_window_start(t), t]) 로 거래가능 종목 × 랭킹 윈도우만 로드(load(as_of)
    전 종목 t 이하 전체 OOM 회피). 룩어헤드 상한 ≤t 유지·tradable 푸시필터. 결과 불변(momentum
    lookback+skip 거래일이 윈도우에 충분 포함). ⚠️ 장기 거래정지(윈도우에 봉 0)인 tradable 종목은
    스테일 모멘텀 없이 랭킹 제외 — full load(as_of) 대비 발산 가능(드묾·의도된 스테일 배제·benchmark
    members 와 동일 계열).
    """
    tradable = universe_port.constituents(as_of=t)
    tradable &= liquidity_port.liquid_tickers(as_of=t, candidates=tradable)
    # B·방식 C(ROE→momentum): liquidity 직후·momentum 전 흑자 필터로 유니버스 축소. off(기본)=
    # 현 흐름 bit-identical(필터 미호출). 벤치도 동일 filter_by_roe 공유(H3 대칭).
    if config.apply_roe_filter and financial_facts is not None:
        tradable = filter_by_roe(
            tradable,
            identity=identity,
            financial_facts=financial_facts,
            as_of=t,
            min_roe=config.min_roe,
            max_age_days=config.roe_max_age_days,
        )
    if isinstance(price_port, MomentumScorePort):
        # SQL 부분 푸시다운(ADR-007) — 끝점 2점만 스캔(1억행 풀로드 회피).
        # load_range+momentum_universe 와 bit-identical(windowed wn·Task2/5 봉인·윈도우 동일 출처).
        scores = price_port.momentum_scores(
            tickers=tradable,
            as_of=t,
            lookback_days=config.lookback_days,
            skip_recent_days=config.skip_recent_days,
        )
    else:
        # Fake/Parquet 폴백 — 랭킹 윈도우만 로드 후 메모리 momentum(MomentumScorePort 미구현 포트).
        series = price_port.load_range(tickers=tradable, start=_window_start(config, t), end=t)
        scores = momentum_universe(
            series,
            as_of=t,
            lookback_days=config.lookback_days,
            skip_recent_days=config.skip_recent_days,
        )
    # rank_by_momentum 은 score!=None ticker 의 exchange 매핑 누락 시 ValueError(None 은 체크 전
    # skip → 제외 무방). 두 경로 scores 키=윈도우 데이터 종목 동일 → 동일 매핑(결과 불변).
    ticker_to_exchange = {
        k: ex for k, ex in exchanges.items() if k in scores and scores[k].score is not None
    }
    # decile 모드면 rank 절단 없이 전 후보(top_n=후보수) → 전략이 상위 pct 선택(분모=후보수·M1).
    # 고정 모드면 config.top_n 절단. 후보수 = momentum 산출(score!=None) 종목 수.
    if config.portfolio_pct is not None:
        n_candidates = sum(1 for ms in scores.values() if ms.score is not None)
        rank_top_n = max(1, n_candidates)
    else:
        rank_top_n = config.top_n
    ranked = rank_by_momentum(
        scores,
        ticker_to_exchange,
        lookback_days=config.lookback_days,
        top_n=rank_top_n,
        group_by_exchange=config.group_by_exchange,
    )
    # cik 앵커 enrich(가능 시) — 생존편향 ticker 재사용 오조인 방지. 미해소면 "" 유지(caveat).
    return [replace(e, cik=identity.cik_for(e.ticker, on=t) or e.cik) for e in ranked]


def _window_start(config: BacktestConfig, t: date) -> date:
    """랭킹 윈도우 하한 — momentum lookback+skip 거래일을 충분히 덮는 캘린더 여유(×2 + 30일).

    `load_range(tradable, start=_window_start(t), end=t)` 로 랭킹 입력을 좁혀 load(as_of) 전 종목
    t 이하 전체(OOM) 회피. 여유(거래일≈캘린더×5/7 → ×2 면 lookback+skip 거래일 확실 포함)가 momentum
    필요 구간을 덮어 결과 불변. 상장 초기 종목은 가용 전부(full load 와 동일 graceful).
    ⚠️ 윈도우 산식은 `ports.momentum_window_days`(단일 출처) — DuckDB momentum_scores 와 동일 보장.
    """
    return t - timedelta(days=momentum_window_days(config.lookback_days, config.skip_recent_days))


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
    return_cap: Decimal,
) -> tuple[Decimal, int, int]:
    """가중 보유수익 + (폐지청산 건수, 진입가 결측 skip 건수).

    폐지(entry<de<=exit)면 recovery_rate 청산.
    A1p2 L4: per-ticker ret 을 **상한 cap 만** 클램프. ret=exit/entry-1 은 entry>0·exit>=0 이라
    수학적으로 ret>=-1(하한은 폭발 불가) — 폭발은 전부 상한(극소 진입가·sentinel exit). 하한 floor
    는 폭발 방어 0이고 정상 손실만 마스킹=낙관편향이라 두지 않음(정직·리뷰 반영).
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
        total += w * min(ret, return_cap)  # 상한만 — 하한은 구조적 -1(폭발 불가)
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
