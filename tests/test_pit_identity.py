"""PitIdentityResolver — 시점별 ticker→cik(생존편향+룩어헤드 정답) 단위 테스트(라이브 0).

핵심 방어(BLOCKING): ① 경계 `on<valid_to`(폐지 마지막날 포함·경계날 배제 — MasterUniverse
`delisted_at+1` 정렬) ② **다중매칭=raise**(스키마에 중첩 EXCLUDE 없음 → resolver 가 유일 방어선)
③ ticker 재사용 시 과거 시점에 미래 엔티티 cik 누설 금지(룩어헤드 sabotage).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from stockpick.backtest.identity import PitIdentityResolver
from stockpick.backtest.ports import IdentityResolver


def _write_history(base_dir: Path, rows: list[dict[str, object]]) -> None:
    payload = {"generated_at": "2026-06-29T00:00:00+00:00", "history": rows}
    (base_dir / "ticker_history.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _row(ticker: str, cik: str | None, valid_from: str, valid_to: str | None) -> dict[str, object]:
    return {"ticker": ticker, "cik": cik, "valid_from": valid_from, "valid_to": valid_to}


def test_implements_identity_resolver_protocol(tmp_path: Path) -> None:
    _write_history(tmp_path, [_row("AAPL", "0000320193", "1980-12-12", None)])
    assert isinstance(PitIdentityResolver(tmp_path), IdentityResolver)


def test_lookahead_sabotage_ticker_reuse(tmp_path: Path) -> None:
    # ticker RUSE 재사용: 엔티티1 cik1[2000~2010폐지]·엔티티2 cik2[2015~현재]. 비중첩 다행.
    _write_history(
        tmp_path,
        [
            _row("RUSE", "0000000001", "2000-01-01", "2010-01-02"),  # 폐지 2010-01-01 +1
            _row("RUSE", "0000000002", "2015-01-01", None),  # 재할당(현재)
        ],
    )
    r = PitIdentityResolver(tmp_path)
    assert r.cik_for("RUSE", on=date(2008, 6, 1)) == "0000000001"  # 과거=엔티티1
    assert r.cik_for("RUSE", on=date(2018, 6, 1)) == "0000000002"  # 미래=엔티티2
    assert r.cik_for("RUSE", on=date(2012, 6, 1)) == ""  # 공백기=미해소(미래 누설 금지·BLOCKING)


def test_boundary_last_trading_day_included_boundary_day_excluded(tmp_path: Path) -> None:
    # valid_to=2010-01-02(폐지 2010-01-01 +1). 마지막 거래일 포함·경계날 배제(on<valid_to).
    _write_history(tmp_path, [_row("DEAD", "0000000003", "2000-01-01", "2010-01-02")])
    r = PitIdentityResolver(tmp_path)
    assert r.cik_for("DEAD", on=date(2010, 1, 1)) == "0000000003"  # 마지막 실거래일 포함
    assert r.cik_for("DEAD", on=date(2010, 1, 2)) == ""  # 경계날 배제
    assert r.cik_for("DEAD", on=date(2000, 1, 1)) == "0000000003"  # valid_from 포함(≤)
    assert r.cik_for("DEAD", on=date(1999, 12, 31)) == ""  # valid_from 이전


def test_multi_match_raises(tmp_path: Path) -> None:
    # 중첩 윈도우(데이터 무결성 버그) → 모호한 식별이면 조용히 추측 금지·명시 raise(BLOCKING).
    _write_history(
        tmp_path,
        [
            _row("OVLP", "0000000004", "2000-01-01", "2012-01-01"),
            _row("OVLP", "0000000005", "2010-01-01", None),  # 2010~2012 중첩
        ],
    )
    r = PitIdentityResolver(tmp_path)
    with pytest.raises(ValueError, match="다중매칭"):
        r.cik_for("OVLP", on=date(2011, 1, 1))


def test_open_window_covers_all_after_valid_from(tmp_path: Path) -> None:
    _write_history(tmp_path, [_row("LIVE", "0000000006", "2005-01-01", None)])
    r = PitIdentityResolver(tmp_path)
    assert r.cik_for("LIVE", on=date(2005, 1, 1)) == "0000000006"
    assert r.cik_for("LIVE", on=date(2099, 1, 1)) == "0000000006"


def test_null_cik_row_returns_empty(tmp_path: Path) -> None:
    # cik 미해소 엔티티(폐지+cik복구 실패) → 윈도우는 있으나 cik="" (추측 금지).
    _write_history(tmp_path, [_row("NOCIK", None, "2000-01-01", "2010-01-02")])
    r = PitIdentityResolver(tmp_path)
    assert r.cik_for("NOCIK", on=date(2005, 1, 1)) == ""


def test_class_shares_same_cik_not_confused_with_reuse(tmp_path: Path) -> None:
    # GOOG·GOOGL = 동일 발행사(동일 cik)·다른 ticker → 각자 독립 해소(재사용 혼동 아님).
    _write_history(
        tmp_path,
        [
            _row("GOOG", "0001652044", "2014-04-03", None),
            _row("GOOGL", "0001652044", "2004-08-19", None),
        ],
    )
    r = PitIdentityResolver(tmp_path)
    assert r.cik_for("GOOG", on=date(2020, 1, 1)) == "0001652044"
    assert r.cik_for("GOOGL", on=date(2020, 1, 1)) == "0001652044"


def test_unresolved_ticker_returns_empty(tmp_path: Path) -> None:
    _write_history(tmp_path, [_row("AAPL", "0000320193", "1980-12-12", None)])
    r = PitIdentityResolver(tmp_path)
    assert r.cik_for("ZZZZ", on=date(2020, 1, 1)) == ""


def test_uppercase_normalized(tmp_path: Path) -> None:
    _write_history(tmp_path, [_row("AAPL", "0000320193", "1980-12-12", None)])
    r = PitIdentityResolver(tmp_path)
    assert r.cik_for("aapl", on=date(2020, 1, 1)) == "0000320193"


def test_missing_file_all_empty(tmp_path: Path) -> None:
    r = PitIdentityResolver(tmp_path)  # ticker_history.json 부재 → 빈 맵(현 동작 유지·에러 아님)
    assert r.cik_for("AAPL", on=date(2020, 1, 1)) == ""
