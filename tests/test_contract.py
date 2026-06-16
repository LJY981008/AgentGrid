"""도메인 계약 스모크 — 타입 import·구성 검증 (네트워크 0)."""

from datetime import date

from stockpick.types import DailyBar, Market, Stock, TopEntry


def test_market_enum() -> None:
    assert Market.KOSPI.value == "KOSPI"
    assert Market.KOSDAQ.value == "KOSDAQ"


def test_stock_delisted_nullable() -> None:
    """폐지 종목은 delisted_at 보존(생존편향 회피), 현재 상장은 None."""
    live = Stock(
        code="005930", name="삼성전자", market=Market.KOSPI, listed_at=None, delisted_at=None
    )
    dead = Stock(
        code="000000",
        name="폐지사",
        market=Market.KOSDAQ,
        listed_at=None,
        delisted_at=date(2020, 1, 1),
    )
    assert live.delisted_at is None
    assert dead.delisted_at == date(2020, 1, 1)


def test_top_entry_carries_rule_version_and_factors() -> None:
    """Top 엔트리는 룰 버전·팩터 기여를 보존(재현성·보정 추적)."""
    e = TopEntry(
        code="005930",
        market=Market.KOSPI,
        rank=1,
        score=0.87,
        rule_version="v0",
        factors={"momentum": 0.4, "value": 0.3, "liquidity": 0.17},
    )
    assert e.rank == 1
    assert e.factors["momentum"] == 0.4


def test_daily_bar_value_nullable() -> None:
    bar = DailyBar(
        code="005930",
        trade_date=date(2024, 1, 2),
        open=70000,
        high=71000,
        low=69500,
        close=70500,
        volume=10_000_000,
        value=None,
    )
    assert bar.value is None
