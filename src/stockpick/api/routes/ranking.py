"""GET /api/ranking — Top 모멘텀 랭킹.

demo.run_demo 가 print 만 하므로 직접 재사용 불가 → 동일 호출 순서를 api 가 조합한다(스캔→as_of→
거래소 매핑→모멘텀→랭킹). 차이는 출력이 표가 아니라 JSON(TopEntry[] + meta)이라는 점뿐이다.

⭐ §4.1 BLOCKING: meta.validated=false + warning 을 **항상** 포함한다(백테스트 검증 전 룰은 알파
아님 — 프론트 경고 배지 상시). 데이터 없음·정상 산출 모두 동일하게 warning 유지.

룩어헤드(BLOCKING)는 하위가 강제: as_of 지정 시 load_adjusted_series 가 trade_date<=as_of 로 1차
가드, factors.momentum 이 2차 가드. api 는 as_of 를 그대로 하위에 위임(미래 누설 방지 책임은 하위).

파라미터 검증: FastAPI Query 제약(ge)으로 범위 위반을 **422** 로 막는다(rules 가 ValueError 던지기
전에 차단 — 422 가 의미상 정확). group 은 Literal 로 enum 검증.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, Query

from ...backtest.s6_gate import load_s6_gate_verdict, ranking_rule_signature
from ...rules._financials import load_financial_facts
from ...rules._scan import load_adjusted_series, load_close_as_of, load_ticker_exchanges
from ...rules.factors import financial_factors, momentum_universe
from ...rules.ranking import rank_by_momentum
from ..deps import get_base_dir, get_identity_resolver
from ..models import RankingMeta, RankingParams, RankingResponse, TopEntryModel

if TYPE_CHECKING:
    from ...backtest.ports import IdentityResolver
    from ...rules.factors import FinancialScore

logger = logging.getLogger(__name__)

router = APIRouter()

_WARNING = "백테스트 검증 전 — 알파 아님(stock-1st_plan §4.1)"
_WARNING_VALIDATED = "S6-b 신뢰성 게이트 통과(OOS 강건성 검증) — 과거 성과는 미래 보장 아님"


def _enrich_factors(base: dict[str, float], score: FinancialScore | None) -> dict[str, float]:
    """모멘텀 factors dict 에 재무 팩터(roe·pb) 추가. 미해소·결측 키는 생략(rank 영향 0·§9-2)."""
    merged = dict(base)
    if score is not None:
        if score.roe is not None:
            merged["roe"] = float(score.roe)
        if score.pb is not None:
            merged["pb"] = float(score.pb)
    return merged


@router.get("/ranking", response_model=RankingResponse)
def ranking(
    base_dir: Path = Depends(get_base_dir),
    as_of: date | None = Query(default=None, description="평가 시점(ISO). 미지정=최신일"),
    lookback_days: int = Query(default=126, ge=1, description="룩백 거래일 수"),
    skip_recent_days: int = Query(default=21, ge=0, description="최근 N거래일 제외(reversal 회피)"),
    top_n: int = Query(default=5, ge=1, description="그룹(또는 전체)별 상위 N"),
    group: Literal["exchange", "all"] = Query(default="exchange", description="랭킹 단위"),
    identity: IdentityResolver = Depends(get_identity_resolver),
) -> RankingResponse:
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
                warning=_WARNING,
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
            warning=_WARNING_VALIDATED if validated else _WARNING,
            as_of=effective_as_of,
            params=params,
            unrankable_tickers=unrankable,
        ),
    )
