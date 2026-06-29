"""폐지 ticker→cik 복구(A1) 단위 테스트 — 라이브 0(fetch 주입)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from stockpick.data.cik_mapping import (
    load_delisted_ciks,
    resolve_delisted_ciks,
    select_delisted_sample,
    store_delisted_ciks,
)


def _stock(ticker: str, delisted_at: str | None, cik: str = "") -> dict[str, object]:
    return {
        "ticker": ticker,
        "delisted_at": delisted_at,
        "cik": cik,
        "listed_at": "2000-01-01",
    }


def test_resolve_maps_ticker_to_cik_with_delisted_date() -> None:
    # fetch 가 cik 주는 폐지 ticker → {ticker:(cik, delisted_date)}. fetch=None 인 ticker 는 제외.
    delisted = [("ENRNQ", date(2001, 12, 2)), ("NOCOV", date(2008, 9, 15))]
    fetch = {"ENRNQ": "0001024401"}.get  # NOCOV → None(미커버)

    result = resolve_delisted_ciks(fetch, delisted)

    assert result == {"ENRNQ": ("0001024401", date(2001, 12, 2))}  # NOCOV 제외(cik 없음)


def test_resolve_empty_input_empty_result() -> None:
    assert resolve_delisted_ciks(lambda _t: None, []) == {}


def test_store_then_load_roundtrip(tmp_path: Path) -> None:
    # 저장본(delisted_cik.json) 직렬화 라운드트립 — cik·날짜 보존.
    mapping = {"ENRNQ": ("0001024401", date(2001, 12, 2))}
    path = store_delisted_ciks(mapping, tmp_path)
    assert path.is_file()
    assert load_delisted_ciks(tmp_path) == mapping


def test_load_missing_file_empty() -> None:
    assert load_delisted_ciks(Path("/nonexistent")) == {}


def test_store_writes_iso_dates(tmp_path: Path) -> None:
    # 저장 형식: ticker → {cik, delisted_date(ISO)}. 사람이 읽고 교차검증 가능.
    store_delisted_ciks({"ENRNQ": ("0001024401", date(2001, 12, 2))}, tmp_path)
    payload = json.loads((tmp_path / "edgar" / "delisted_cik.json").read_text(encoding="utf-8"))
    assert payload["ENRNQ"] == {"cik": "0001024401", "delisted_date": "2001-12-02"}


def test_select_sample_only_delisted_unresolved() -> None:
    # 모집단 = 폐지(delisted_at≠null) ∧ cik 미해소(생존편향 갭). 현재사·해소사 제외.
    stocks = [
        _stock("ACTIVE", None),  # 현재사 — 제외
        _stock("RESOLVED", "2010-01-01", cik="0000111111"),  # cik 있음 — 제외(갭 아님)
        _stock("GAP1", "2010-01-01"),
        _stock("GAP2", "2011-01-01"),
    ]
    out = select_delisted_sample(stocks, 10)
    assert sorted(t for t, _ in out) == ["GAP1", "GAP2"]


def test_select_sample_returns_ticker_date_pairs() -> None:
    out = select_delisted_sample([_stock("GAP1", "2010-03-04")], 10)
    assert out == [("GAP1", date(2010, 3, 4))]


def test_select_sample_even_spacing_deterministic() -> None:
    # ticker 정렬 후 균등 stride 추출 — 알파벳/시대 편중 회피·재현 가능(라이브 0).
    stocks = [_stock(f"T{i:03d}", "2010-01-01") for i in range(100)]
    out = select_delisted_sample(stocks, 5)
    assert [t for t, _ in out] == ["T000", "T020", "T040", "T060", "T080"]  # stride=20
    assert select_delisted_sample(stocks, 5) == out  # 결정성


def test_select_sample_n_ge_population_returns_all() -> None:
    stocks = [_stock("A", "2010-01-01"), _stock("B", "2011-01-01")]
    assert [t for t, _ in select_delisted_sample(stocks, 10)] == ["A", "B"]
