"""랭킹 오케스트레이션 서비스 — `/api/ranking` 라우트와 추적 라운드 스냅샷 캡처가 **공유**.

routes/ranking.py 인라인이던 스캔→as_of→유동성→rank→cik/재무 enrich→validated 흐름을 행위
보존 추출(M4 P6). 라운드 생성(POST /api/rounds)이 같은 함수로 Top20 을 캡처해 랭킹 화면과
스냅샷의 산출 경로가 단일 출처가 된다(중복 구현 드리프트 차단).

⚡ 메모리(2026-07-02): 이전엔 `load_adjusted_series`(전 트리 ≤as_of 풀로드)로 50k×26년을
메모리에 올려 12g OOM(실측 exit 137). 이제 **유동성 필터를 momentum 앞으로** 옮기고
`_select_price_port`(cache.duckdb 있으면 `MomentumScorePort` 끝점 푸시다운·ADR-007)로 산출한다.
유동 후보는 전부 최근 데이터를 가지므로 **windowed momentum == 전-시계열 momentum**(bit-identical)
— 엔진 `_rank_at` 과 동일 경로라 validated decile 룰과도 정합(전 트리 풀로드 회피).

⭐ §4.1 BLOCKING: meta.validated 는 S6-b 게이트 판정(rule_signature 일치)만 true — 그 외
warning 상시. 룩어헤드는 하위(momentum_endpoints·load_range trade_date≤as_of·factors)가 강제.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from ..backtest.adapters import (
    _close_liquidity_port,
    _close_price_port,
    _select_liquidity_port,
    _select_price_port,
)
from ..backtest.config import (
    _DEFAULT_ADV_WINDOW_DAYS,
    _DEFAULT_MIN_ADV_DOLLAR,
    _DEFAULT_MIN_PRICE_FLOOR,
)
from ..backtest.ports import MomentumScorePort, momentum_window_days
from ..backtest.s6_gate import load_s6_gate_verdict, ranking_rule_signature
from ..rules._financials import load_financial_facts_for
from ..rules._scan import load_close_as_of
from ..rules.factors import financial_factors, momentum_universe
from ..rules.ranking import rank_by_momentum
from ..types import Exchange
from .models import RankingMeta, RankingParams, RankingResponse, TopEntryModel

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet
    from datetime import date
    from pathlib import Path

    from ..backtest.ports import IdentityResolver, PriceSeriesPort
    from ..rules.factors import FinancialScore, MomentumScore

logger = logging.getLogger(__name__)

WARNING_UNVALIDATED = "백테스트 검증 전 — 알파 아님(stock-1st_plan §4.1)"
WARNING_VALIDATED = "S6-b 신뢰성 게이트 통과(OOS 강건성 검증) — 과거 성과는 미래 보장 아님"


def _enrich_factors(base: dict[str, float], score: FinancialScore | None) -> dict[str, float]:
    """모멘텀 factors dict 에 재무 팩터(roe·pb) 추가. 미해소·결측 키는 생략(rank 영향 0·§9-2)."""
    merged = dict(base)
    if score is not None:
        if score.roe is not None:
            merged["roe"] = float(score.roe)
        if score.pb is not None:
            merged["pb"] = float(score.pb)
    return merged


def _empty(params: RankingParams) -> RankingResponse:
    """데이터 없음 → 빈 엔트리·as_of null. warning 유지(200·에러 아님 — 첫 실행 정상 상태)."""
    logger.info("ranking: 데이터셋 비어있음 — 빈 랭킹 반환")
    return RankingResponse(
        entries=[],
        meta=RankingMeta(
            validated=False,
            warning=WARNING_UNVALIDATED,
            as_of=None,
            params=params,
            unrankable_tickers=[],
        ),
    )


_SNAPSHOT_NAME = "stock_snapshot.json"


def _ticker_exchanges(base_dir: Path, price_port: PriceSeriesPort) -> dict[str, Exchange]:
    """ticker→Exchange — **stock_snapshot.json(PG파생·소형)** 우선(수만 종목 즉시). 부재/파싱실패면
    `price_port.ticker_exchanges()`(Parquet 전 트리 GROUP BY·수GB·수십초) 폴백.

    스냅샷 = stock 마스터(유니버스 단일 출처·MasterUniverse 와 동일 소스). 유동성 필터가 가격
    없는 마스터 종목을 걸러내므로 후보 소스로 안전. exchange 미인식 종목은 건너뜀(폴백 아님).
    """
    snap = base_dir / _SNAPSHOT_NAME
    if snap.is_file():
        try:
            payload = json.loads(snap.read_text(encoding="utf-8"))
            stocks = payload["stocks"]
        except (OSError, ValueError, KeyError):
            logger.warning("stock_snapshot.json 파싱 실패 — Parquet ticker_exchanges 폴백")
        else:
            out: dict[str, Exchange] = {}
            for stock in stocks:
                try:
                    out[str(stock["ticker"])] = Exchange(str(stock["exchange"]))
                except (KeyError, ValueError):
                    continue  # exchange 미인식 — 조용히 건너뜀(전체 폴백 아님)
            if out:
                return out
    logger.info("ticker_exchanges: 스냅샷 부재 — Parquet 스캔 폴백(느림)")
    return price_port.ticker_exchanges()


def _momentum_scores(
    price_port: PriceSeriesPort,
    tickers: AbstractSet[str],
    *,
    as_of: date,
    lookback_days: int,
    skip_recent_days: int,
) -> dict[str, MomentumScore]:
    """유동 후보 momentum — 엔진 `_rank_at` 과 동일 분기(cache 푸시다운·부재 시 windowed).

    두 경로 모두 윈도우만 스캔 → 전 트리 풀로드 회피(OOM 해소). 유동 후보는 최근 데이터
    보유라 windowed = 전-시계열 momentum(bit-identical·factors 봉인·엔진 정합).
    """
    if not tickers:
        return {}
    if isinstance(price_port, MomentumScorePort):
        return price_port.momentum_scores(
            tickers=set(tickers),
            as_of=as_of,
            lookback_days=lookback_days,
            skip_recent_days=skip_recent_days,
        )
    window_days = momentum_window_days(lookback_days, skip_recent_days)
    series = price_port.load_range(
        tickers=set(tickers), start=as_of - timedelta(days=window_days), end=as_of
    )
    return momentum_universe(
        series, as_of=as_of, lookback_days=lookback_days, skip_recent_days=skip_recent_days
    )


def compute_ranking(
    base_dir: Path,
    identity: IdentityResolver,
    *,
    as_of: date | None,
    lookback_days: int,
    skip_recent_days: int,
    top_n: int,
    group: str,
) -> RankingResponse:
    """Top-N 모멘텀 랭킹 산출(유동성 선필터→momentum 푸시다운→rank→enrich→validated).

    반환은 pydantic 응답 그대로(라우트는 pass-through, 라운드 캡처는 entries/meta 를 스냅샷
    으로 동결). group: "exchange"|"all"(Literal 검증은 라우트 Query 책임).
    """
    group_by_exchange = group == "exchange"
    params = RankingParams(
        lookback_days=lookback_days,
        skip_recent_days=skip_recent_days,
        top_n=top_n,
        group=group,
    )

    price_port = _select_price_port(base_dir)
    try:
        exchanges = _ticker_exchanges(base_dir, price_port)  # 스냅샷 우선(즉시)·Parquet 폴백
        days = price_port.trading_days()
        if not exchanges or not days:
            return _empty(params)
        # as_of 미지정이면 데이터셋 최신 거래일로 확정. 지정 시 그대로(룩어헤드 상한은 하위 강제).
        effective_as_of = as_of if as_of is not None else max(days)

        # (c) PIT 유동성 필터를 **momentum 앞**에 — 후보를 유동 종목으로 먼저 좁혀 전 트리 스캔을
        # 피하고, 남은 후보가 전부 최근 데이터를 가져 windowed momentum 이 전-시계열과 일치한다.
        # cache 있으면 검증 decile 과 동일 유니버스($5·ADV $1M), 부재면 Noop(WARNING·전 후보).
        liquidity_port = _select_liquidity_port(
            base_dir,
            min_price=_DEFAULT_MIN_PRICE_FLOOR,
            min_adv=_DEFAULT_MIN_ADV_DOLLAR,
            window=_DEFAULT_ADV_WINDOW_DAYS,
        )
        try:
            liquid = liquidity_port.liquid_tickers(
                as_of=effective_as_of, candidates=set(exchanges)
            )
        finally:
            _close_liquidity_port(liquidity_port)

        scores = _momentum_scores(
            price_port,
            liquid,
            as_of=effective_as_of,
            lookback_days=lookback_days,
            skip_recent_days=skip_recent_days,
        )
    finally:
        _close_price_port(price_port)

    entries = rank_by_momentum(
        scores,
        exchanges,
        lookback_days=lookback_days,
        top_n=top_n,
        group_by_exchange=group_by_exchange,
    )

    # 산출 불가(score=None) 종목 — 조용한 누락 금지, meta 에 명시 고지(결정적 정렬).
    unrankable = sorted(t for t, s in scores.items() if s.score is None)

    # cik enrich(api 층) — EDGAR 저장본으로 ticker→cik 해소(미해소면 기존 빈값, rules 불변).
    entry_cik = {
        e.ticker: (identity.cik_for(e.ticker, on=effective_as_of) or e.cik) for e in entries
    }

    # 재무 팩터 enrich(밸류 P/B·퀄리티 ROE) — ⚠️ rank 순서·점수 불변(§9-2 결합 안 함, factors dict
    # 에 정보 추가만). 가격은 명목 raw close(P/B 일관성). 미해소 cik·재무 결측 → 해당 키 생략.
    entry_tickers = {e.ticker for e in entries}
    entry_ciks = {c for c in entry_cik.values() if c}
    financial_facts = load_financial_facts_for(base_dir, entry_ciks)
    raw_close = load_close_as_of(base_dir, as_of=effective_as_of, tickers=entry_tickers)
    price_by_cik = {
        cik: raw_close[e.ticker]
        for e in entries
        if (cik := entry_cik[e.ticker]) and e.ticker in raw_close
    }
    fin_scores = financial_factors(
        financial_facts,
        ciks=list(entry_ciks),
        as_of=effective_as_of,
        price_by_cik=price_by_cik,
    )

    # validated flip(S6-b·R4) — 게이트는 decile momentum 을 검증. 운영 Top5 는 그 decile 의 상위
    # 부분집합이라 display top_n 은 signature 와 무관(ranking_rule_signature 가 decile 정규값 채움).
    # 요청 momentum(lookback/skip/group)이 검증 decile 과 일치할 때만 true(그 외 false 보수).
    validated = load_s6_gate_verdict(
        base_dir,
        ranking_rule_signature(
            lookback_days=lookback_days,
            skip_recent_days=skip_recent_days,
            group_by_exchange=group_by_exchange,
        ),
    )

    return RankingResponse(
        entries=[
            TopEntryModel(
                cik=entry_cik[e.ticker],
                ticker=e.ticker,
                exchange=e.exchange,
                rank=e.rank,
                score=e.score,
                rule_version=e.rule_version,
                factors=_enrich_factors(e.factors, fin_scores.get(entry_cik[e.ticker])),
            )
            for e in entries
        ],
        meta=RankingMeta(
            validated=validated,
            warning=WARNING_VALIDATED if validated else WARNING_UNVALIDATED,
            as_of=effective_as_of,
            params=params,
            unrankable_tickers=unrankable,
        ),
    )
