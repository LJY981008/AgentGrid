"""backtest/adapters MasterUniverse·_select_universe — 생존편향 유니버스(경계 변환·degenerate).

핵심 = 경계 pin(BLOCKING): 스냅샷 `delisted_at`(마지막 실거래일)을 `+1day`(첫 거래불가일)로 변환해
engine/Fake/Protocol 규약과 통일 — 마지막 실거래일 거래가능 유지·청산가=마지막 실봉. 라이브 0.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pytest

from stockpick.backtest.adapters import (
    MasterUniverse,
    PriceDerivedUniverse,
    _select_universe,
)
from stockpick.backtest.fakes import FakePriceSeriesPort, FakeUniversePort


def _write_snapshot(base_dir: Path, stocks: list[dict[str, object]]) -> None:
    payload = {"generated_at": "2026-06-22T00:00:00+00:00", "stocks": stocks}
    (base_dir / "stock_snapshot.json").write_text(json.dumps(payload), encoding="utf-8")


def _s(
    ticker: str,
    listed: str | None,
    delisted: str | None = None,
    status: str = "active",
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "cik": None,
        "name": ticker,
        "exchange": "NASDAQ",
        "listed_at": listed,
        "delisted_at": delisted,
        "listing_status": status,
    }


def test_master_universe_boundary_and_membership(tmp_path: Path) -> None:
    # 경계 pin(BLOCKING): 폐지 DEAD 마지막거래일 D=2008-09-15 → boundary D+1.
    _write_snapshot(
        tmp_path,
        [
            _s("ACT", "2000-01-01"),  # active
            _s("FUT", "2030-01-01"),  # 미래상장
            _s("DEAD", "2001-01-01", "2008-09-15", "delisted"),  # 폐지
        ],
    )
    mu = MasterUniverse(tmp_path)
    # 마지막 실거래일 당일 포함·D+1 배제(실봉 소실 방지)
    assert "DEAD" in mu.constituents(as_of=date(2008, 9, 15))
    assert "DEAD" not in mu.constituents(as_of=date(2008, 9, 16))
    # boundary=D+1 → engine _price_before(boundary)=D 봉(마지막 실봉 청산)
    assert mu.delisting_event("DEAD") == date(2008, 9, 16)
    assert mu.delisting_event("ACT") is None
    # 미래상장 배제·active 포함
    assert "FUT" not in mu.constituents(as_of=date(2020, 1, 1))
    assert "FUT" in mu.constituents(as_of=date(2030, 1, 1))
    assert "ACT" in mu.constituents(as_of=date(2020, 1, 1))
    assert mu.ticker_count() == 3


def test_master_universe_degenerate_and_none_excluded(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # listed>=delisted drop·listed None 제외 — 조용한 소실 금지(WARNING 검증).
    _write_snapshot(
        tmp_path,
        [
            _s("OK", "2000-01-01"),
            _s("DEGEN", "2010-01-01", "2010-01-01", "delisted"),
            _s("NOPRICE", None),
        ],
    )
    with caplog.at_level(logging.WARNING):
        mu = MasterUniverse(tmp_path)
    assert mu.ticker_count() == 1  # OK 만
    assert mu.constituents(as_of=date(2020, 1, 1)) == {"OK"}
    assert "degenerate" in caplog.text  # 조용한 소실 금지 — drop 시 WARNING 발화


def test_master_universe_equiv_fakeuniverseport(tmp_path: Path) -> None:
    # 변환 규약 봉인: MasterUniverse(delisted=D) ≡ FakeUniversePort(boundary=D+1).
    _write_snapshot(tmp_path, [_s("DEAD", "2001-01-01", "2008-09-15", "delisted")])
    mu = MasterUniverse(tmp_path)
    fake = FakeUniversePort(
        listed={"DEAD": date(2001, 1, 1)},
        delisted={"DEAD": date(2008, 9, 16)},  # Fake 의 delisted=첫 거래불가일=boundary=D+1
    )
    for as_of in (date(2008, 9, 14), date(2008, 9, 15), date(2008, 9, 16)):
        assert mu.constituents(as_of=as_of) == fake.constituents(as_of=as_of)
    assert mu.delisting_event("DEAD") == fake.delisting_event("DEAD")


def test_master_universe_future_delisting_still_active(tmp_path: Path) -> None:
    # 미래 폐지(2030) 종목은 현재(2020) as_of 에 거래가능(룩어헤드 방어).
    _write_snapshot(tmp_path, [_s("LIVE", "2000-01-01", "2030-01-01", "delisted")])
    mu = MasterUniverse(tmp_path)
    assert "LIVE" in mu.constituents(as_of=date(2020, 1, 1))
    assert mu.delisting_event("LIVE") == date(2030, 1, 2)


def test_select_universe_snapshot_present(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, [_s("X", "2000-01-01")])
    u = _select_universe(tmp_path, FakePriceSeriesPort({}))
    assert isinstance(u, MasterUniverse)


def test_select_universe_snapshot_absent(tmp_path: Path) -> None:
    # 스냅샷 부재 → PriceDerivedUniverse 폴백(골격·생존편향 미방어).
    u = _select_universe(tmp_path, FakePriceSeriesPort({}))
    assert isinstance(u, PriceDerivedUniverse)
