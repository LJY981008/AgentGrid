from datetime import date, timedelta

import pytest

from stockpick.backtest.calendar import holding_periods, rebalance_dates


def _trading_days(start: date, n: int) -> list[date]:
    # 주말 제외 근사(테스트용 — 실제론 데이터의 거래일 집합)
    days: list[date] = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def test_holding_periods_entry_is_day_after_rebalance() -> None:
    # 진입 = 리밸일 t 다음 거래일(룩어헤드 t+1). 청산 = 다음 리밸의 진입일. 앵커 = 첫 거래일.
    td = _trading_days(date(2024, 1, 1), 200)
    plan = holding_periods(td, start=td[0], end=td[-1], freq="monthly")
    reb = rebalance_dates(td, freq="monthly")
    assert plan.anchor == td[0]
    assert len(plan.periods) >= 1
    for t, entry, exit_ in plan.periods:
        assert t in reb  # 리밸일
        assert entry > t  # 진입은 t 초과(t+1 — 동시성 누설 차단)
        assert entry <= exit_  # 유효 구간만
    # 인접 구간 seam: 한 구간 청산 = 다음 구간 진입(겹침/공백 없음)
    for (_t1, _e1, x1), (_t2, e2, _x2) in zip(plan.periods, plan.periods[1:], strict=False):
        assert x1 == e2


def test_holding_periods_empty_when_no_data() -> None:
    plan = holding_periods([], start=date(2024, 1, 1), end=date(2024, 12, 31), freq="monthly")
    assert plan.anchor is None
    assert plan.periods == []


def test_monthly_picks_first_trading_day_of_each_month() -> None:
    td = _trading_days(date(2024, 1, 1), 200)  # ~9.5개월
    reb = rebalance_dates(td, freq="monthly")
    months = [(d.year, d.month) for d in reb]
    assert months == sorted(set(months))  # 월별 1개·정렬
    assert reb[0] == td[0]


def test_quarterly_subset_of_monthly() -> None:
    td = _trading_days(date(2024, 1, 1), 260)
    q = rebalance_dates(td, freq="quarterly")
    assert all(d.month in (1, 4, 7, 10) for d in q)


def test_unknown_freq_raises() -> None:
    with pytest.raises(ValueError, match="rebalance_freq"):
        rebalance_dates(_trading_days(date(2024, 1, 1), 10), freq="weekly")


def test_empty_input_empty_output() -> None:
    assert rebalance_dates([], freq="monthly") == []
