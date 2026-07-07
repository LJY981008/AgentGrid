"""M4 P3 data 층 — fetch_splits(EODHD 모킹)·price_read(raw close 로더). 라이브 0.

fetch_splits: /splits/{SYMBOL}.US · split "4.000000/1.000000" 분수 파싱(신주/구주)·파싱 실패
명시 실패. price_read: raw close(adj_factor **미합성** — 분할 보정은 SPLIT 이벤트 책임)·
티커·기간 한정·max trade_date(공통 as-of 입력).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from stockpick.data.eodhd import EodhdSource
from stockpick.data.price_read import load_max_trade_dates, load_raw_close_range
from stockpick.data.storage import write_daily_bars
from stockpick.types import DailyBar, Exchange, Stock

_FAKE_KEY = "test-key-not-real"


@pytest.fixture(autouse=True)
def _set_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EODHD_API_KEY", _FAKE_KEY)


def _source(rows: list[dict[str, object]]) -> EodhdSource:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=rows)

    return EodhdSource(client=httpx.Client(transport=httpx.MockTransport(_handler)))


# ── fetch_splits ────────────────────────────────────────────────────────────


def test_fetch_splits_parses_fraction() -> None:
    src = _source(
        [
            {"date": "2020-08-31", "split": "4.000000/1.000000"},
            {"date": "2014-06-09", "split": "7.000000/1.000000"},
        ]
    )
    splits = src.fetch_splits("AAPL")
    assert splits == [
        (date(2014, 6, 9), Decimal("7")),
        (date(2020, 8, 31), Decimal("4")),
    ]  # effective_on 오름차순·ratio=신주/구주


def test_fetch_splits_reverse_split_ratio_below_one() -> None:
    src = _source([{"date": "2023-01-05", "split": "1.000000/10.000000"}])
    splits = src.fetch_splits("XYZ")
    assert splits == [(date(2023, 1, 5), Decimal("0.1"))]  # 1:10 역분할


def test_fetch_splits_bad_fraction_raises() -> None:
    src = _source([{"date": "2023-01-05", "split": "무엇"}])
    with pytest.raises(ValueError, match="split"):
        src.fetch_splits("XYZ")


def test_fetch_splits_zero_denominator_raises() -> None:
    src = _source([{"date": "2023-01-05", "split": "2.000000/0.000000"}])
    with pytest.raises(ValueError, match="split"):
        src.fetch_splits("XYZ")


def test_fetch_splits_sends_range_and_symbol() -> None:
    seen: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[])

    src = EodhdSource(client=httpx.Client(transport=httpx.MockTransport(_handler)))
    assert src.fetch_splits("SPY", start=date(2020, 1, 1), end=date(2026, 1, 1)) == []
    assert seen["path"] == "/api/splits/SPY.US"
    params = seen["params"]
    assert isinstance(params, dict)
    assert params["fmt"] == "json"
    assert params["from"] == "2020-01-01"
    assert params["to"] == "2026-01-01"


# ── price_read ──────────────────────────────────────────────────────────────


def _bar(ticker: str, d: date, close: str, *, adj: str = "1") -> DailyBar:
    return DailyBar(
        ticker=ticker,
        trade_date=d,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=1000,
        value=None,
        adj_factor=Decimal(adj),
    )


@pytest.fixture
def price_tree(tmp_path: Path) -> Path:
    base = tmp_path / "parquet"
    bars = [
        _bar("AAA", date(2026, 7, 1), "100"),
        _bar("AAA", date(2026, 7, 2), "110", adj="0.5"),  # adj≠1 — raw 미합성 검증용
        _bar("AAA", date(2026, 7, 3), "120"),
        _bar("BBB", date(2026, 7, 1), "50"),
        _bar("BBB", date(2026, 7, 2), "55"),
    ]
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=base, source="test")
    return base


def test_load_raw_close_range_returns_raw_not_adjusted(price_tree: Path) -> None:
    out = load_raw_close_range(
        price_tree, tickers={"AAA"}, start=date(2026, 7, 1), end=date(2026, 7, 3)
    )
    assert list(out) == ["AAA"]
    # adj_factor 0.5 인 7/2 도 raw 110 그대로(수정주가 미합성 — 분할 보정은 SPLIT 이벤트 책임).
    assert out["AAA"] == [
        (date(2026, 7, 1), Decimal("100")),
        (date(2026, 7, 2), Decimal("110")),
        (date(2026, 7, 3), Decimal("120")),
    ]


def test_load_raw_close_range_filters_tickers_and_window(price_tree: Path) -> None:
    out = load_raw_close_range(
        price_tree, tickers={"AAA", "BBB"}, start=date(2026, 7, 2), end=date(2026, 7, 2)
    )
    assert out["AAA"] == [(date(2026, 7, 2), Decimal("110"))]
    assert out["BBB"] == [(date(2026, 7, 2), Decimal("55"))]


def test_load_raw_close_range_empty_inputs(price_tree: Path, tmp_path: Path) -> None:
    assert load_raw_close_range(
        price_tree, tickers=set(), start=date(2026, 7, 1), end=date(2026, 7, 3)
    ) == {}
    empty = tmp_path / "none"
    assert load_raw_close_range(
        empty, tickers={"AAA"}, start=date(2026, 7, 1), end=date(2026, 7, 3)
    ) == {}


def test_load_max_trade_dates(price_tree: Path) -> None:
    out = load_max_trade_dates(price_tree, tickers={"AAA", "BBB", "ZZZ"})
    assert out == {"AAA": date(2026, 7, 3), "BBB": date(2026, 7, 2)}  # ZZZ 무데이터=키 없음


# ── benchmark sync(SPY 격리 서브트리) ───────────────────────────────────────


class _FakeBarSource:
    """DataSource 최소 구현 — fetch_daily_bars 만 실사용(벤치 동기화)."""

    name = "fake"

    def __init__(self, bars: list[DailyBar]) -> None:
        self._bars = bars

    def iter_universe(self, *, include_delisted: bool = True) -> list[Stock]:  # noqa: ARG002
        return []

    def fetch_daily_bars(
        self,
        ticker: str,  # noqa: ARG002
        *,
        start: date | None = None,  # noqa: ARG002
        end: date | None = None,  # noqa: ARG002
    ) -> list[DailyBar]:
        return self._bars


def test_sync_benchmark_writes_isolated_subtree(tmp_path: Path) -> None:
    from stockpick.data.benchmark import BENCHMARK_SUBDIR, sync_benchmark_prices

    base = tmp_path / "parquet"
    bars = [_bar("SPY", date(2026, 7, 1), "500"), _bar("SPY", date(2026, 7, 2), "505")]
    assert sync_benchmark_prices(base, _FakeBarSource(bars)) == 2
    # 본트리(daily_bar) 오염 없음 — 격리 서브트리에만 적재.
    assert not (base / "daily_bar").exists()
    out = load_raw_close_range(
        base / BENCHMARK_SUBDIR, tickers={"SPY"}, start=date(2026, 7, 1), end=date(2026, 7, 2)
    )
    assert out["SPY"] == [(date(2026, 7, 1), Decimal("500")), (date(2026, 7, 2), Decimal("505"))]


def test_sync_benchmark_zero_rows_no_tree(tmp_path: Path) -> None:
    from stockpick.data.benchmark import BENCHMARK_SUBDIR, sync_benchmark_prices

    base = tmp_path / "parquet"
    assert sync_benchmark_prices(base, _FakeBarSource([])) == 0
    assert not (base / BENCHMARK_SUBDIR).exists()  # 조용한 빈 벤치 트리 금지
