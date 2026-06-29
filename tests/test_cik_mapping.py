"""폐지 ticker→cik 복구(A1) 단위 테스트 — 라이브 0(fetch 주입)."""

from __future__ import annotations

import json
from datetime import date

from stockpick.data.cik_mapping import (
    load_delisted_ciks,
    resolve_delisted_ciks,
    store_delisted_ciks,
)


def test_resolve_maps_ticker_to_cik_with_delisted_date() -> None:
    # fetch 가 cik 주는 폐지 ticker → {ticker:(cik, delisted_date)}. fetch=None 인 ticker 는 제외.
    delisted = [("ENRNQ", date(2001, 12, 2)), ("NOCOV", date(2008, 9, 15))]
    fetch = {"ENRNQ": "0001024401"}.get  # NOCOV → None(미커버)

    result = resolve_delisted_ciks(fetch, delisted)

    assert result == {"ENRNQ": ("0001024401", date(2001, 12, 2))}  # NOCOV 제외(cik 없음)


def test_resolve_empty_input_empty_result() -> None:
    assert resolve_delisted_ciks(lambda _t: None, []) == {}


def test_store_then_load_roundtrip(tmp_path) -> None:  # noqa: ANN001
    # 저장본(delisted_cik.json) 직렬화 라운드트립 — cik·날짜 보존.
    mapping = {"ENRNQ": ("0001024401", date(2001, 12, 2))}
    path = store_delisted_ciks(mapping, tmp_path)
    assert path.is_file()
    assert load_delisted_ciks(tmp_path) == mapping


def test_load_missing_file_empty() -> None:
    from pathlib import Path

    assert load_delisted_ciks(Path("/nonexistent")) == {}


def test_store_writes_iso_dates(tmp_path) -> None:  # noqa: ANN001
    # 저장 형식: ticker → {cik, delisted_date(ISO)}. 사람이 읽고 교차검증 가능.
    store_delisted_ciks({"ENRNQ": ("0001024401", date(2001, 12, 2))}, tmp_path)
    payload = json.loads((tmp_path / "edgar" / "delisted_cik.json").read_text(encoding="utf-8"))
    assert payload["ENRNQ"] == {"cik": "0001024401", "delisted_date": "2001-12-02"}
