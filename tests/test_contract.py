"""도메인 계약 스모크 — 타입 import·구성 검증 (네트워크 0, 미국 계약)."""

from datetime import date
from decimal import Decimal

from stockpick.data.source import DataSource
from stockpick.types import DailyBar, Exchange, Stock, TopEntry


def test_exchange_is_strenum() -> None:
    """Exchange 는 StrEnum — 값이 곧 문자열(직렬화·비교 자연 동작, UP042 해소)."""
    assert Exchange.NYSE == "NYSE"
    assert Exchange.NASDAQ.value == "NASDAQ"
    # StrEnum 멤버는 str 인스턴스 — 가격 소스 응답 문자열과 직접 비교 가능
    assert isinstance(Exchange.NASDAQ, str)
    assert f"{Exchange.NYSE_AMERICAN}" == "NYSE_AMERICAN"


def test_stock_has_stable_cik_and_volatile_ticker() -> None:
    """안정 식별자 cik + 시변 ticker 동시 보유, 폐지는 delisted_at 보존(생존편향 회피)."""
    live = Stock(
        cik="0000320193",
        ticker="AAPL",
        name="Apple Inc.",
        exchange=Exchange.NASDAQ,
        listed_at=None,
        delisted_at=None,
    )
    dead = Stock(
        cik="0000037996",
        ticker="F-OLD",
        name="폐지/심볼변경 예시사",
        exchange=Exchange.NYSE,
        listed_at=None,
        delisted_at=date(2018, 6, 1),
    )
    assert live.cik == "0000320193"
    assert live.ticker == "AAPL"
    assert live.delisted_at is None
    assert dead.delisted_at == date(2018, 6, 1)


def test_daily_bar_keyed_by_ticker_decimal_price() -> None:
    """일봉 키는 ticker(가격 소스 키), 거래대금 미제공 None, 가격 Decimal, 무수정 adj_factor=1."""
    bar = DailyBar(
        ticker="AAPL",
        trade_date=date(2024, 1, 2),
        open=Decimal("187.15"),
        high=Decimal("188.44"),
        low=Decimal("183.89"),
        close=Decimal("185.64"),
        volume=82_488_700,
        value=None,
    )
    assert bar.ticker == "AAPL"
    assert bar.value is None
    assert isinstance(bar.close, Decimal)
    assert bar.adj_factor == Decimal("1")


def test_top_entry_anchored_on_cik_carries_rule_version_and_factors() -> None:
    """Top 엔트리는 cik 앵커(폐지 ticker 재사용 오조인 방지) + 룰 버전·팩터 기여 보존."""
    e = TopEntry(
        cik="0000320193",
        ticker="AAPL",
        exchange=Exchange.NASDAQ,
        rank=1,
        score=0.87,
        rule_version="v0",
        factors={"momentum": 0.4, "value": 0.3, "quality": 0.17},
    )
    assert e.cik == "0000320193"
    assert e.rank == 1
    assert e.factors["momentum"] == 0.4


def test_datasource_protocol_runtime_smoke() -> None:
    """DataSource 는 runtime_checkable Protocol — 구조적 구현체가 isinstance 로 인식되는지 스모크.

    네트워크 0: 픽스처 스텁이 계약 메서드를 구조적으로 만족하면 DataSource 로 통과해야 한다.
    """

    class _StubSource:
        @property
        def name(self) -> str:
            return "stub"

        def iter_universe(self, *, include_delisted: bool = True) -> list[Stock]:
            return []

        def fetch_daily_bars(
            self,
            ticker: str,
            *,
            start: date | None = None,
            end: date | None = None,
        ) -> list[DailyBar]:
            return []

    stub = _StubSource()
    assert isinstance(stub, DataSource)
    assert stub.name == "stub"
    assert stub.iter_universe() == []
    assert stub.fetch_daily_bars("AAPL") == []

    # 메서드가 빠진 객체는 Protocol 을 만족하지 않아야 한다(구조 누락 감지)
    assert not isinstance(object(), DataSource)
