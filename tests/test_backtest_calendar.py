from datetime import date, timedelta

import pytest

from stockpick.backtest.calendar import rebalance_dates


def _trading_days(start: date, n: int) -> list[date]:
    # 주말 제외 근사(테스트용 — 실제론 데이터의 거래일 집합)
    days: list[date] = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


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
