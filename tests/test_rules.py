"""룰엔진(rules) 단위 테스트 — 합성 시계열·라이브 0(DuckDB/파일/네트워크 미사용).

factors·ranking 은 순수 함수라 합성 PricePoint 로 정확값을 단언한다(_scan 의 DuckDB I/O 는 라이브
의존이라 이 단위 테스트 범위 밖 — qa-tester 가 데모 라이브로 실동작 확인).

검증 항목:
- 모멘텀 정확값: 알려진 가격 시계열의 누적수익률을 손계산값과 일치(Decimal 정밀).
- ⭐ 룩어헤드 안전성(금융 BLOCKING 회귀 봉인): as_of 이후 데이터를 추가해도 as_of 점수 불변
  (미래 누설 0). 이 테스트가 미래누설 버그를 잡는지 sabotage 로도 확인했다.
- 1개월 제외(skip_recent_days): end 점이 과거로 밀려 점수가 바뀜.
- graceful 축소: 룩백이 데이터보다 길면 가용 최장으로 축소(used_window_points 명시).
- 랭킹: 점수 내림차순·rank 1-based·동점(competition ranking)·TopN 절단·거래소별 그룹·TopEntry 필드.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from stockpick.rules._scan import PricePoint
from stockpick.rules.factors import momentum, momentum_universe
from stockpick.rules.ranking import rank_by_momentum
from stockpick.types import Exchange, TopEntry

_BASE = date(2025, 1, 1)


def _series(prices: list[str], *, start: date = _BASE) -> list[PricePoint]:
    """연속 거래일(주말 무시 — 테스트는 추상 거래일 인덱스) 수정주가 시계열 생성."""
    return [
        PricePoint(trade_date=start + timedelta(days=i), adjusted=Decimal(p))
        for i, p in enumerate(prices)
    ]


# ---------------------------------------------------------------------------
# 모멘텀 정확값
# ---------------------------------------------------------------------------
def test_momentum_exact_value() -> None:
    # 100→110, lookback=1 거래일: 110/100-1 = 0.10
    series = _series(["100", "110"])
    as_of = series[-1].trade_date
    result = momentum(series, as_of=as_of, lookback_days=1)
    assert result.score == Decimal("0.1")
    assert result.start_date == series[0].trade_date
    assert result.end_date == series[1].trade_date
    assert result.used_window_points == 2


def test_momentum_multi_day_cumulative() -> None:
    # 100→120 over 4 거래일, lookback=4: 120/100-1 = 0.20 (중간 경로 무관 — 끝점 비율)
    series = _series(["100", "105", "90", "130", "120"])
    as_of = series[-1].trade_date
    result = momentum(series, as_of=as_of, lookback_days=4)
    assert result.score == Decimal("0.2")
    assert result.used_window_points == 5


def test_momentum_negative_return() -> None:
    series = _series(["200", "150"])  # -25%
    result = momentum(series, as_of=series[-1].trade_date, lookback_days=1)
    assert result.score == Decimal("-0.25")


# ---------------------------------------------------------------------------
# ⭐ 룩어헤드 안전성 (금융 BLOCKING 회귀 봉인)
# ---------------------------------------------------------------------------
def test_momentum_lookahead_safety_future_data_ignored() -> None:
    """as_of 이후 데이터를 추가해도 as_of 점수가 변하지 않아야 한다(미래 누설 0).

    이게 핵심 회귀 봉인: factors.momentum 이 trade_date<=as_of 만 쓰는지 검증. 만약 미래 행을
    포함해 계산하면(룩어헤드 버그) 아래 두 점수가 달라져 테스트가 실패한다.
    """
    base_series = _series(["100", "110", "120"])
    as_of = base_series[-1].trade_date  # 2025-01-03

    score_before = momentum(base_series, as_of=as_of, lookback_days=2)

    # as_of 이후 미래 데이터를 붙인다(가격이 폭등 — 미래를 보면 점수가 크게 달라질 것).
    future_series = [
        *base_series,
        PricePoint(trade_date=as_of + timedelta(days=1), adjusted=Decimal("999")),
        PricePoint(trade_date=as_of + timedelta(days=2), adjusted=Decimal("9999")),
    ]
    score_after = momentum(future_series, as_of=as_of, lookback_days=2)

    # as_of 점수는 미래 데이터 유무와 무관해야 한다(룩어헤드 BLOCKING).
    assert score_before.score == score_after.score
    assert score_after.score == Decimal("0.2")  # 120/100-1, 999/9999 미반영
    assert score_after.end_date == as_of  # end 가 미래로 새지 않음


def test_momentum_as_of_in_past_uses_only_past() -> None:
    """as_of 가 시계열 중간이면 그 이전 점만으로 계산(미래 구간 무시)."""
    series = _series(["100", "110", "120", "500", "600"])
    mid_as_of = series[2].trade_date  # 120 시점
    result = momentum(series, as_of=mid_as_of, lookback_days=2)
    assert result.score == Decimal("0.2")  # 120/100-1, 500·600 미반영
    assert result.end_date == mid_as_of


# ---------------------------------------------------------------------------
# 최근 N일 제외(reversal 회피)
# ---------------------------------------------------------------------------
def test_momentum_skip_recent_shifts_end() -> None:
    # 점: 100,110,120,130. skip_recent=1 → end=120(130 제외), lookback=2 → start=100.
    series = _series(["100", "110", "120", "130"])
    as_of = series[-1].trade_date
    result = momentum(series, as_of=as_of, lookback_days=2, skip_recent_days=1)
    assert result.end_date == series[2].trade_date  # 120 (130 제외됨)
    assert result.score == Decimal("0.2")  # 120/100-1


# ---------------------------------------------------------------------------
# graceful 축소
# ---------------------------------------------------------------------------
def test_momentum_graceful_clamp_when_lookback_exceeds_data() -> None:
    # 점 3개인데 lookback=100 → start 를 가장 오래된 점(100)으로 clamp.
    series = _series(["100", "150", "200"])
    as_of = series[-1].trade_date
    result = momentum(series, as_of=as_of, lookback_days=100)
    assert result.score == Decimal("1.0")  # 200/100-1
    assert result.start_date == series[0].trade_date
    assert result.requested_lookback_days == 100
    assert result.used_window_points == 3  # 가용 전체


# ---------------------------------------------------------------------------
# 산출 불가 케이스
# ---------------------------------------------------------------------------
def test_momentum_insufficient_points_returns_none() -> None:
    series = _series(["100"])  # 점 1개 — 시작·끝 둘 다 필요한데 부족
    result = momentum(series, as_of=series[-1].trade_date, lookback_days=1)
    assert result.score is None


def test_momentum_nonpositive_start_returns_none() -> None:
    # start 수정주가<=0 — 0/음수 나눗셈 불가, None(조용한 왜곡 금지).
    series = [
        PricePoint(trade_date=_BASE, adjusted=Decimal("0")),
        PricePoint(trade_date=_BASE + timedelta(days=1), adjusted=Decimal("100")),
    ]
    result = momentum(series, as_of=series[-1].trade_date, lookback_days=1)
    assert result.score is None


def test_momentum_invalid_lookback_raises() -> None:
    with pytest.raises(ValueError, match="lookback_days"):
        momentum(_series(["100", "110"]), as_of=_BASE, lookback_days=0)


# ---------------------------------------------------------------------------
# 랭킹
# ---------------------------------------------------------------------------
def _universe() -> dict[str, list[PricePoint]]:
    # 1 거래일 lookback 으로 명확한 순서: AAA 50%, BBB 20%, CCC -10%
    return {
        "AAA": _series(["100", "150"]),  # +50%
        "BBB": _series(["100", "120"]),  # +20%
        "CCC": _series(["100", "90"]),  # -10%
    }


def _exchanges() -> dict[str, Exchange]:
    return {"AAA": Exchange.NASDAQ, "BBB": Exchange.NYSE, "CCC": Exchange.NASDAQ}


def test_ranking_order_and_1based_rank() -> None:
    uni = _universe()
    as_of = uni["AAA"][-1].trade_date
    scores = momentum_universe(uni, as_of=as_of, lookback_days=1)
    entries = rank_by_momentum(scores, _exchanges(), lookback_days=1, top_n=5)

    assert [e.ticker for e in entries] == ["AAA", "BBB", "CCC"]
    assert [e.rank for e in entries] == [1, 2, 3]  # 1-based
    assert entries[0].score == pytest.approx(0.5)
    assert entries[0].rule_version == "v0-momentum-1"
    assert entries[0].factors == {"momentum": pytest.approx(0.5)}
    assert entries[0].cik == ""  # EODHD 미제공 — ticker 식별
    assert entries[0].exchange == Exchange.NASDAQ
    assert all(isinstance(e, TopEntry) for e in entries)


def test_ranking_topn_truncation() -> None:
    uni = _universe()
    as_of = uni["AAA"][-1].trade_date
    scores = momentum_universe(uni, as_of=as_of, lookback_days=1)
    entries = rank_by_momentum(scores, _exchanges(), lookback_days=1, top_n=2)
    assert [e.ticker for e in entries] == ["AAA", "BBB"]  # 상위 2만


def test_ranking_ties_competition_ranking_and_deterministic() -> None:
    """동점 처리: 같은 점수는 같은 rank(competition: 1,1,3), 순서는 ticker 오름차순(결정적)."""
    uni = {
        "ZZZ": _series(["100", "110"]),  # +10%
        "AAA": _series(["100", "110"]),  # +10% (ZZZ 와 동점)
        "MMM": _series(["100", "90"]),  # -10%
    }
    exch = {"ZZZ": Exchange.NASDAQ, "AAA": Exchange.NASDAQ, "MMM": Exchange.NASDAQ}
    as_of = uni["AAA"][-1].trade_date
    scores = momentum_universe(uni, as_of=as_of, lookback_days=1)
    entries = rank_by_momentum(scores, exch, lookback_days=1, top_n=5)

    # 동점 2개는 같은 rank(1), 순서는 ticker 오름차순(AAA 먼저). 그 다음 MMM 은 rank 3.
    assert [(e.ticker, e.rank) for e in entries] == [("AAA", 1), ("ZZZ", 1), ("MMM", 3)]


def test_ranking_excludes_unrankable_scores() -> None:
    # 데이터 부족(점 1개)인 종목은 랭킹에서 제외(조용한 포함 금지).
    uni = {
        "AAA": _series(["100", "150"]),  # +50%
        "BAD": _series(["100"]),  # 점 1개 — score=None
    }
    exch = {"AAA": Exchange.NASDAQ, "BAD": Exchange.NASDAQ}
    as_of = uni["AAA"][-1].trade_date
    scores = momentum_universe(uni, as_of=as_of, lookback_days=1)
    entries = rank_by_momentum(scores, exch, lookback_days=1, top_n=5)
    assert [e.ticker for e in entries] == ["AAA"]  # BAD 제외


def test_ranking_group_by_exchange() -> None:
    uni = _universe()
    as_of = uni["AAA"][-1].trade_date
    scores = momentum_universe(uni, as_of=as_of, lookback_days=1)
    entries = rank_by_momentum(
        scores, _exchanges(), lookback_days=1, top_n=5, group_by_exchange=True
    )
    # NASDAQ: AAA(+50%) rank1, CCC(-10%) rank2 / NYSE: BBB(+20%) rank1.
    by_exch: dict[Exchange, list[tuple[str, int]]] = {}
    for e in entries:
        by_exch.setdefault(e.exchange, []).append((e.ticker, e.rank))
    assert by_exch[Exchange.NASDAQ] == [("AAA", 1), ("CCC", 2)]
    assert by_exch[Exchange.NYSE] == [("BBB", 1)]


def test_ranking_missing_exchange_raises() -> None:
    # 거래소 미상 종목은 추측 채움 금지 — 명시적 ValueError.
    uni = {"AAA": _series(["100", "150"])}
    as_of = uni["AAA"][-1].trade_date
    scores = momentum_universe(uni, as_of=as_of, lookback_days=1)
    with pytest.raises(ValueError, match="거래소 미상"):
        rank_by_momentum(scores, {}, lookback_days=1, top_n=5)


def test_ranking_invalid_topn_raises() -> None:
    with pytest.raises(ValueError, match="top_n"):
        rank_by_momentum({}, {}, lookback_days=1, top_n=0)


def test_ranking_empty_universe() -> None:
    assert rank_by_momentum({}, {}, lookback_days=1, top_n=5) == []
