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

if TYPE_CHECKING:
    from datetime import date

    from ._scan import PricePoint

logger = logging.getLogger(__name__)


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
