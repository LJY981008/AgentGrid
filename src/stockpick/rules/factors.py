"""가격기반 팩터 — 시점 as_of 에서 각 종목의 점수 산출(룩어헤드 2차 방어선).

팩터(factor)란 "어느 시점 as_of 에서 종목을 줄 세우는 수치"다. 이 모듈은 **순수 계산**만 한다 —
입력은 이미 로드된 수정주가 시계열(`_scan.PricePoint`), 출력은 종목별 Decimal 점수. DuckDB·파일·
네트워크에 의존하지 않아 합성 데이터로 정확값 단위 테스트가 가능하다(라이브 0).

⚠️ 룩어헤드 BLOCKING(2차 방어선): as_of 의 점수는 **trade_date <= as_of 인 점만** 사용한다.
_scan 이 SQL 에서 1차로 막지만, 여기서도 명시적으로 한 번 더 필터한다(미래 누설 0 회귀 봉인 —
테스트 test_rules 가 as_of 이후 데이터를 추가해도 점수 불변임을 단언한다). 시점 t 결정에 >t 데이터
사용은 백테스트 무효(python-conventions §금융).

⚠️ 수정주가 BLOCKING: 입력 adjusted 는 배당·분할 보정 가격이다(원본 불변, _scan 에서 합성). 모멘텀은
adjusted 비율로만 계산한다 — raw close 비율은 배당·분할 점프로 왜곡된다.

⚠️ 이건 프로토타입 골격이다(stock-1st_plan §4.1): 모멘텀 1종·룩백은 후보일 뿐, 최종 팩터셋·룩백·
가중치는 M2 백테스트(§4.4)가 결정한다. 백테스트 검증 전 이 점수를 알파로 신뢰 금지(과적합 경고).

모듈 경계(python-conventions): `rules` 는 `data`·`..types` 만 의존. 이 파일은 외부 의존 0(stdlib).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from ._financials import latest_as_of

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date

    from ..types import FinancialFact
    from ._scan import PricePoint

logger = logging.getLogger(__name__)

# 슬라이스 concept(ADR-005) — edgar._SLICE_CONCEPTS 의 bare tag 와 일치해야 함(드리프트 주의).
_CONCEPT_EQUITY = "StockholdersEquity"  # 자기자본(USD) — ROE 분모·P/B 분모 BVPS
_CONCEPT_NET_INCOME = "NetIncomeLoss"  # 순이익(USD·연간) — ROE 분자
_CONCEPT_SHARES = "EntityCommonStockSharesOutstanding"  # 주식수(dei) — P/B BVPS 분모


@dataclass(frozen=True, slots=True)
class MomentumScore:
    """모멘텀 산출 결과 — 점수 + 산출 근거(투명성·재현성).

    score = (P_end / P_start - 1) (수정주가 누적수익률, 소수 비율). 룩백이 데이터보다 길면 가용
    최장 구간으로 graceful 축소하며(window_days = 실제 사용 거래일 수), used_lookback_days 로
    "요청 룩백"과 "실제 사용 구간"을 구분 기록한다(조용한 축소 금지 — 명시).

    start_date/end_date = 실제 사용한 두 끝점의 trade_date(근거 추적). score=None 이면 산출 불가
    (점이 2개 미만 — 비율 계산에 시작·끝 둘 다 필요).
    """

    score: Decimal | None
    end_date: date | None
    start_date: date | None
    requested_lookback_days: int
    used_window_points: int  # 실제 사용한 점 개수(시작·끝 포함, graceful 축소 반영)


def momentum(
    series: list[PricePoint],
    *,
    as_of: date,
    lookback_days: int,
    skip_recent_days: int = 0,
) -> MomentumScore:
    """단일 종목 수정주가 시계열 → as_of 시점 모멘텀(누적수익률). 룩어헤드 2차 방어선.

    정의(stock-1st_plan §4.2): 모멘텀 = N거래일 누적 수익률 = P_end / P_start - 1. 가격은 수정주가
    (adjusted). 거래일(trading-day) 기준 lookback 이다(역일/캘린더일 아님 — 251 거래일≈1년).

    파라미터:
      - as_of: 평가 시점. 이 날짜 **이하**(trade_date <= as_of) 점만 사용(룩어헤드 BLOCKING).
      - lookback_days: 룩백 거래일 수. end 점에서 과거로 lookback_days 칸 떨어진 점을 start 로 쓴다.
      - skip_recent_days: 최근 N거래일 제외(reversal 회피 — §4.2 "최근 1개월 제외" 표준 관행).
        end 점을 as_of 가 아니라 as_of 에서 N칸 과거로 잡는다. 0 이면 제외 없음(end = 최신 가용일).

    graceful 축소: 룩백이 가용 데이터보다 길면 **가장 오래된 점을 start 로** 써 가용 최장 구간으로
    축소한다(조용한 축소 금지 — MomentumScore.used_window_points 와 start_date 로 명시 보고).

    산출 불가(score=None): as_of 이하 점이 2개 미만(start·end 둘 다 필요) 또는 skip 적용 후 점
    부족. start 의 adjusted<=0(0/음수 나눗셈 불가)도 None(조용한 왜곡 금지 — _adjust 와 일관).

    Java 비유: 정렬된 List<PricePoint> 에서 끝 인덱스와 (끝-lookback) 인덱스를 잡아 비율을 내되,
    인덱스가 음수면 0(가장 오래된 점)으로 clamp — 미래(as_of 초과)는 애초에 stream 에서 뺀다.
    """
    if lookback_days < 1:
        msg = f"lookback_days 는 1 이상이어야 함(받음={lookback_days})"
        raise ValueError(msg)
    if skip_recent_days < 0:
        msg = f"skip_recent_days 는 0 이상이어야 함(받음={skip_recent_days})"
        raise ValueError(msg)

    # 룩어헤드 2차 방어선: as_of 이하만(미래 누설 0). 입력이 정렬돼 있어도 방어적으로 재필터·정렬.
    eligible = sorted(
        (p for p in series if p.trade_date <= as_of),
        key=lambda p: p.trade_date,
    )

    none_result = MomentumScore(
        score=None,
        end_date=None,
        start_date=None,
        requested_lookback_days=lookback_days,
        used_window_points=0,
    )

    # end 점: skip_recent_days 만큼 최근 제외(reversal 회피). end_idx = eligible 끝에서 skip 칸 앞.
    end_idx = len(eligible) - 1 - skip_recent_days
    if end_idx < 1:
        # end 점이 없거나(skip 과다) start 를 둘 공간이 없음(2점 미만) — 산출 불가.
        logger.debug(
            "모멘텀 산출 불가(점 부족): eligible=%d, skip=%d, as_of=%s",
            len(eligible),
            skip_recent_days,
            as_of,
        )
        return none_result

    # start 점: end 에서 lookback_days 칸 과거. 데이터보다 길면 0(최古 점)으로 clamp(graceful).
    start_idx = end_idx - lookback_days
    clamped = start_idx < 0
    if clamped:
        start_idx = 0

    start = eligible[start_idx]
    end = eligible[end_idx]
    used_points = end_idx - start_idx + 1

    if start.adjusted <= 0:
        # 수정주가<=0(0/음수 나눗셈) — 조용한 왜곡 금지, None + WARNING(_adjust 와 일관 보수 처리).
        logger.warning(
            "모멘텀 산출 불가(start 수정주가<=0): start_date=%s, adjusted=%s",
            start.trade_date,
            start.adjusted,
        )
        return none_result

    score = end.adjusted / start.adjusted - Decimal(1)
    if clamped:
        logger.debug(
            "모멘텀 룩백 graceful 축소: 요청=%d거래일, 실제=%d점(%s~%s)",
            lookback_days,
            used_points,
            start.trade_date,
            end.trade_date,
        )
    return MomentumScore(
        score=score,
        end_date=end.trade_date,
        start_date=start.trade_date,
        requested_lookback_days=lookback_days,
        used_window_points=used_points,
    )


def momentum_universe(
    series_by_ticker: dict[str, list[PricePoint]],
    *,
    as_of: date,
    lookback_days: int,
    skip_recent_days: int = 0,
) -> dict[str, MomentumScore]:
    """유니버스 전체에 momentum 적용 → {ticker: MomentumScore}. 산출 불가 종목도 포함(명시).

    score=None 종목(데이터 부족)도 맵에 남긴다 — 랭킹 단계가 "산출 불가"를 알고 제외할 수 있게
    (조용한 누락 금지). 빈 유니버스면 빈 맵.
    """
    scores = {
        ticker: momentum(
            points,
            as_of=as_of,
            lookback_days=lookback_days,
            skip_recent_days=skip_recent_days,
        )
        for ticker, points in series_by_ticker.items()
    }
    rankable = sum(1 for s in scores.values() if s.score is not None)
    logger.info(
        "모멘텀 산출: 유니버스=%d, 랭킹가능=%d, 산출불가=%d, as_of=%s, lookback=%d, skip=%d",
        len(scores),
        rankable,
        len(scores) - rankable,
        as_of,
        lookback_days,
        skip_recent_days,
    )
    return scores


def momentum_from_endpoints(
    *,
    end_point: PricePoint | None,
    start_point: PricePoint | None,
    end_idx: int,
    start_idx: int,
    lookback_days: int,
) -> MomentumScore:
    """SQL 부분 푸시다운 끝점 → MomentumScore (ADR-007·`momentum()` 산출 코어와 bit-identical).

    `end_idx`/`start_idx` = **윈도우** eligible([lo,as_of]·ASC) **0-based idx**(DuckDB 가
    윈도우 count(wn) 기준 산출 — `momentum(windowed)` 의 `end_idx=len-1-skip`·`max(0,end_idx-lb)`
    와 동일). 산출식·None 조건·used_window_points 는 `momentum()`(factors.py) 과 동일:
    end_idx<1(2점미만)·start.adjusted<=0 → None. ⚠️ 나눗셈은 Python Decimal(SQL float 승격 회피).
    """
    none_result = MomentumScore(
        score=None,
        end_date=None,
        start_date=None,
        requested_lookback_days=lookback_days,
        used_window_points=0,
    )
    if end_point is None or start_point is None or end_idx < 1:
        return none_result
    if start_point.adjusted <= 0:
        # 수정주가<=0(0/음수 나눗셈) — 조용한 왜곡 금지, None + WARNING(momentum() 코어와 일관).
        logger.warning(
            "모멘텀 산출 불가(start 수정주가<=0·pushdown): start_date=%s, adjusted=%s",
            start_point.trade_date,
            start_point.adjusted,
        )
        return none_result
    score = end_point.adjusted / start_point.adjusted - Decimal(1)
    return MomentumScore(
        score=score,
        end_date=end_point.trade_date,
        start_date=start_point.trade_date,
        requested_lookback_days=lookback_days,
        used_window_points=end_idx - start_idx + 1,
    )


@dataclass(frozen=True, slots=True)
class FinancialScore:
    """재무 팩터 — ROE(퀄리티)·P/B(밸류) + 산출 근거(투명성·재현성).

    ROE = 최신 연간(FY) NetIncomeLoss / 최신 연간 StockholdersEquity (슬라이스 단순화 — TTM
    4분기합은 후속). P/B = price(as_of) / BVPS, BVPS = StockholdersEquity / shares
    (= 시가총액/자기자본). 산출 불가(결측·분모<=0·가격 결측)→해당 값 None(조용한 추측 금지).

    ⚠️ 이 점수는 정보 노출용이다 — 모멘텀과 **결합·가중 안 함**(§9-2 가중치는 백테스트가 결정).
    재무팩터 노출이 검증을 뜻하지 않는다(meta.validated=false 불변).

    근거 필드(None=미해소): equity/net_income/shares/price = 사용한 원시 입력, *_period =
    선택된 fiscal_period(룩어헤드 추적 — disclosed_at<=as_of 중 최신).
    """

    roe: Decimal | None
    pb: Decimal | None
    equity: Decimal | None
    net_income: Decimal | None
    shares: Decimal | None
    price: Decimal | None
    equity_period: str | None
    net_income_period: str | None


def financial_factors(
    facts: list[FinancialFact],
    *,
    ciks: Iterable[str],
    as_of: date,
    price_by_cik: dict[str, Decimal] | None = None,
    max_age_days: int | None = None,
) -> dict[str, FinancialScore]:
    """cik 별 재무 팩터(ROE·P/B) 산출. 순수 계산(facts·price 입력, 네트워크 없음)·PIT.

    각 cik 에 대해 `_financials.latest_as_of`(disclosed_at<=as_of) 로 PIT 선택:
      - equity = 최신 연간 StockholdersEquity (annual_only — ROE/BVPS 기준)
      - net_income = 최신 연간 NetIncomeLoss (annual_only)
      - shares = 최신 EntityCommonStockSharesOutstanding (annual_only=False — 최신 가용)
    ROE = net_income/equity, P/B = price*shares/equity. **ROE 산출 조건(B·H8)**: equity·net_income
    이 **동일 회계연도(period_end 일치)** ∧ **equity>0**(자본잠식 배제 — 음 equity 우량주도 배제·
    설계 명문) ∧ 결측 아님. period_end 불일치(equity FY24·income FY23 등)=ROE None(왜곡 방지).
    **max_age_days**(H5·STALE 상한): 지정 시 disclosed_at 가 as_of 로부터 그 일수 이내인 fact 만
    (폐지직전 stale 흑자 차단). 분모<=0·결측·가격 결측·FY불일치·stale → 해당 값 None. 미해소 cik 도
    맵에 남긴다(전부 None — 랭킹이 "산출 불가"를 알게, 조용한 누락 금지).
    """
    prices = price_by_cik or {}
    # 성능(H6·BLOCKING): cik별 1회 인덱싱 → latest_as_of 가 전체 facts(만-cik 2.68M) 대신 해당 cik
    # 부분집합만 스캔. 순진 호출은 O(ciks × 전체 facts)/리밸 = 게이트 OOM/타임아웃. (결과 불변.)
    facts_by_cik: dict[str, list[FinancialFact]] = {}
    for fact in facts:
        facts_by_cik.setdefault(fact.cik, []).append(fact)
    result: dict[str, FinancialScore] = {}
    for cik in ciks:
        cik_facts = facts_by_cik.get(cik, [])
        equity_fact = latest_as_of(
            cik_facts, concept=_CONCEPT_EQUITY, cik=cik, as_of=as_of, annual_only=True,
            max_age_days=max_age_days,
        )
        income_fact = latest_as_of(
            cik_facts, concept=_CONCEPT_NET_INCOME, cik=cik, as_of=as_of, annual_only=True,
            max_age_days=max_age_days,
        )
        shares_fact = latest_as_of(
            cik_facts, concept=_CONCEPT_SHARES, cik=cik, as_of=as_of, max_age_days=max_age_days
        )
        price = prices.get(cik)

        equity = equity_fact.value if equity_fact is not None else None
        net_income = income_fact.value if income_fact is not None else None
        shares = shares_fact.value if shares_fact is not None else None

        roe: Decimal | None = None
        # 동일 FY(period_end 일치) 강제 — 서로 다른 회계연도 조합은 흑자/적자 판정 왜곡(H8).
        same_fy = (
            equity_fact is not None
            and income_fact is not None
            and equity_fact.period_end == income_fact.period_end
        )
        if same_fy and equity is not None and equity > 0 and net_income is not None:
            roe = net_income / equity

        pb: Decimal | None = None
        if (
            price is not None
            and equity is not None
            and equity > 0
            and shares is not None
            and shares > 0
        ):
            pb = price * shares / equity

        result[cik] = FinancialScore(
            roe=roe,
            pb=pb,
            equity=equity,
            net_income=net_income,
            shares=shares,
            price=price,
            equity_period=equity_fact.fiscal_period if equity_fact is not None else None,
            net_income_period=income_fact.fiscal_period if income_fact is not None else None,
        )

    with_roe = sum(1 for s in result.values() if s.roe is not None)
    with_pb = sum(1 for s in result.values() if s.pb is not None)
    logger.info(
        "재무 팩터 산출: cik=%d, ROE해소=%d, P/B해소=%d, as_of=%s",
        len(result),
        with_roe,
        with_pb,
        as_of,
    )
    return result
