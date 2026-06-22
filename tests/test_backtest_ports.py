from datetime import date
from decimal import Decimal

from stockpick.backtest.adapters import PriceDerivedUniverse
from stockpick.backtest.fakes import (
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.ports import IdentityResolver, PriceSeriesPort, UniversePort
from stockpick.rules._scan import PricePoint


def test_price_derived_universe_constituents_from_first_trade_date() -> None:
    # 가격기반 유니버스 — listed=첫 거래일, 폐지 없음(골격 차선). UniversePort Protocol 충족.
    series = {
        "A": [
            PricePoint(date(2024, 1, 2), Decimal("10")),
            PricePoint(date(2024, 3, 1), Decimal("11")),
        ],
        "B": [PricePoint(date(2024, 2, 1), Decimal("20"))],  # B 는 2024-02 첫 등장
    }
    uni = PriceDerivedUniverse(FakePriceSeriesPort(series))
    assert isinstance(uni, UniversePort)
    assert uni.constituents(as_of=date(2024, 1, 15)) == {"A"}  # B 아직 첫거래일 전
    assert uni.constituents(as_of=date(2024, 2, 15)) == {"A", "B"}
    assert uni.delisting_event("A") is None  # 가격기반엔 폐지 정보 없음
    assert uni.ticker_count() == 2


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakePriceSeriesPort({}), PriceSeriesPort)
    assert isinstance(FakeUniversePort({}, {}), UniversePort)
    assert isinstance(StubIdentityResolver({}), IdentityResolver)


def test_universe_constituents_excludes_future_and_delisted() -> None:
    uni = FakeUniversePort(
        listed={"A": date(2023, 1, 1), "B": date(2024, 6, 1)},  # B 는 2024-06 상장
        delisted={"A": date(2024, 3, 1)},  # A 는 2024-03 폐지
    )
    # 2024-02-01: A 거래가능(상장·미폐지), B 미상장
    assert uni.constituents(as_of=date(2024, 2, 1)) == {"A"}
    # 2024-07-01: A 폐지·B 상장
    assert uni.constituents(as_of=date(2024, 7, 1)) == {"B"}
    assert uni.delisting_event("A") == date(2024, 3, 1)
    assert uni.delisting_event("B") is None


def test_price_port_load_filters_as_of() -> None:
    series = {
        "A": [
            PricePoint(date(2024, 1, 2), Decimal("10")),
            PricePoint(date(2024, 2, 1), Decimal("11")),
        ]
    }
    port = FakePriceSeriesPort(series)
    loaded = port.load(as_of=date(2024, 1, 15))
    assert [p.trade_date for p in loaded["A"]] == [date(2024, 1, 2)]
    # full_series 는 전구간
    assert len(port.full_series()["A"]) == 2
    assert port.trading_days() == [date(2024, 1, 2), date(2024, 2, 1)]


def test_fake_load_range_slices_tickers_and_dates() -> None:
    # S6-a: load_range = tickers∩ × [start,end] 슬라이스·빈 window ticker 제외(_scan 동치).
    series = {
        "A": [
            PricePoint(date(2024, 1, 2), Decimal("10")),
            PricePoint(date(2024, 1, 5), Decimal("11")),
            PricePoint(date(2024, 1, 10), Decimal("12")),
        ],
        "B": [PricePoint(date(2024, 1, 3), Decimal("20"))],
    }
    port = FakePriceSeriesPort(series)
    rng = port.load_range(tickers={"A"}, start=date(2024, 1, 4), end=date(2024, 1, 8))
    assert set(rng) == {"A"}  # B 제외(tickers 필터)
    assert [p.trade_date for p in rng["A"]] == [date(2024, 1, 5)]  # [4,8] 내 = 5만(경계 포함)
    # 빈 window ticker 제외 + 빈 tickers → {}
    assert port.load_range(tickers={"A"}, start=date(2024, 1, 6), end=date(2024, 1, 7)) == {}
    assert port.load_range(tickers=set(), start=date(2024, 1, 1), end=date(2024, 1, 31)) == {}


def test_stub_identity_resolver() -> None:
    r = StubIdentityResolver({"AAPL": "0000320193"})
    assert r.cik_for("AAPL", on=date(2024, 1, 1)) == "0000320193"
    assert r.cik_for("UNKNOWN", on=date(2024, 1, 1)) == ""  # 미해소 → 빈 문자열(caveat)
