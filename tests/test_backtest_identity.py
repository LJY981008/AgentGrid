"""EdgarSnapshotResolver — IdentityResolver 구현 단위 테스트(라이브 0·저장본만 읽음)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from stockpick.backtest.identity import EdgarSnapshotResolver
from stockpick.backtest.ports import IdentityResolver
from stockpick.data.edgar import store_ticker_cik


def test_implements_identity_resolver_protocol(tmp_path: Path) -> None:
    store_ticker_cik({"AAPL": "0000320193"}, tmp_path)
    assert isinstance(EdgarSnapshotResolver(tmp_path), IdentityResolver)


def test_resolves_ticker_uppercase(tmp_path: Path) -> None:
    store_ticker_cik({"AAPL": "0000320193", "NVDA": "0001045810"}, tmp_path)
    r = EdgarSnapshotResolver(tmp_path)
    assert r.cik_for("AAPL", on=date(2024, 1, 1)) == "0000320193"
    assert r.cik_for("aapl", on=date(2024, 1, 1)) == "0000320193"  # 대문자 정규화


def test_unresolved_ticker_returns_empty(tmp_path: Path) -> None:
    store_ticker_cik({"AAPL": "0000320193"}, tmp_path)
    r = EdgarSnapshotResolver(tmp_path)
    assert r.cik_for("UNKNOWN", on=date(2024, 1, 1)) == ""  # 미해소 → "" (추측 금지)


def test_missing_store_all_empty(tmp_path: Path) -> None:
    r = EdgarSnapshotResolver(tmp_path)  # 저장본 없음 → 빈 맵
    assert r.cik_for("AAPL", on=date(2024, 1, 1)) == ""


def test_on_date_ignored_snapshot(tmp_path: Path) -> None:
    store_ticker_cik({"AAPL": "0000320193"}, tmp_path)
    r = EdgarSnapshotResolver(tmp_path)
    # 스냅샷 — 시점 무관 동일 결과(history 는 후속에서 on 사용)
    assert r.cik_for("AAPL", on=date(2010, 1, 1)) == r.cik_for("AAPL", on=date(2026, 1, 1))
