"""랭킹 오케스트레이션 서비스 — `/api/ranking` 라우트와 추적 라운드 스냅샷 캡처가 **공유**.

routes/ranking.py 인라인이던 스캔→as_of→유동성→rank→cik/재무 enrich→validated 흐름을 행위
보존 추출(M4 P6). 라운드 생성(POST /api/rounds)이 같은 함수로 Top20 을 캡처해 랭킹 화면과
스냅샷의 산출 경로가 단일 출처가 된다(중복 구현 드리프트 차단).

⭐ §4.1 BLOCKING: meta.validated 는 S6-b 게이트 판정(rule_signature 일치)만 true — 그 외
warning 상시. 룩어헤드는 하위(load_adjusted_series ≤as_of·factors)가 강제.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..backtest.adapters import _close_liquidity_port, _select_liquidity_port
from ..backtest.config import (
    _DEFAULT_ADV_WINDOW_DAYS,
    _DEFAULT_MIN_ADV_DOLLAR,
    _DEFAULT_MIN_PRICE_FLOOR,
)
from ..backtest.s6_gate import load_s6_gate_verdict, ranking_rule_signature
from ..rules._financials import load_financial_facts
from ..rules._scan import load_adjusted_series, load_close_as_of, load_ticker_exchanges
from ..rules.factors import financial_factors, momentum_universe
from ..rules.ranking import rank_by_momentum
from .models import RankingMeta, RankingParams, RankingResponse, TopEntryModel

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from ..backtest.ports import IdentityResolver
    from ..rules.factors import FinancialScore

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
    """Top-N 모멘텀 랭킹 산출(스캔→유동성→rank→enrich→validated) — 행위 보존 추출.

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

    # as_of 를 그대로 하위에 위임 — 지정 시 SQL 1차 룩어헤드 가드(trade_date<=as_of) 발동.
    series = load_adjusted_series(base_dir, as_of=as_of)
    if not series:
        # 데이터 없음 → 빈 엔트리·as_of null. warning 은 유지(200, 에러 아님 — 첫 실행 정상 상태).
        logger.info("ranking: Parquet 트리 비어있음 — 빈 랭킹 반환")
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

    # as_of 미지정이면 데이터셋 최신 거래일로 확정(demo.run_demo 와 동일 — 룩어헤드는 이미 ≤as_of).
    effective_as_of = (
        as_of if as_of is not None else max(p.trade_date for pts in series.values() for p in pts)
    )

    ticker_to_exchange = load_ticker_exchanges(base_dir)
    scores = momentum_universe(
        series,
        as_of=effective_as_of,
        lookback_days=lookback_days,
        skip_recent_days=skip_recent_days,
    )

    # (c) 사후 PIT 유동성 필터(ADR-010·rules 불변·모듈경계 — api 가 data/backtest 조합).
    # cache.duckdb 있으면 검증 decile 과 동일 유니버스($5·ADV $1M)로 좁혀 display 일관,
    # 부재면 Noop(WARNING). rank_by_momentum 불변 — 입력 scores 만 선필터(룩어헤드 ≤as_of).
    liquidity_port = _select_liquidity_port(
        base_dir,
        min_price=_DEFAULT_MIN_PRICE_FLOOR,
        min_adv=_DEFAULT_MIN_ADV_DOLLAR,
        window=_DEFAULT_ADV_WINDOW_DAYS,
    )
    try:
        liquid = liquidity_port.liquid_tickers(as_of=effective_as_of, candidates=set(scores))
    finally:
        _close_liquidity_port(liquidity_port)
    scores = {t: s for t, s in scores.items() if t in liquid}

    entries = rank_by_momentum(
        scores,
        ticker_to_exchange,
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
    financial_facts = load_financial_facts(base_dir)
    raw_close = load_close_as_of(base_dir, as_of=effective_as_of)
    price_by_cik = {
        cik: raw_close[e.ticker]
        for e in entries
        if (cik := entry_cik[e.ticker]) and e.ticker in raw_close
    }
    fin_scores = financial_factors(
        financial_facts,
        ciks=[c for c in entry_cik.values() if c],
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
