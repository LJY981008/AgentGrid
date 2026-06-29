"""build_ticker_history_rows / _detect_overlaps — 순수 빌더 단위 테스트(PG·라이브 0).

A2 실 다행 ticker_history: valid_from=listed_at·valid_to=delisted_at+1(MasterUniverse 경계 정렬).
cik 우선순위 stock.cik > A1 복구 > None. 룩어헤드 핵심: 폐지 엔티티는 cik 미해소여도 윈도우를 남겨
재사용 ticker 의 과거 시점이 미래 cik 로 누설되지 않게 한다(빈 윈도우면 미래행이 전구간 매칭).
"""

from __future__ import annotations

from datetime import date

from stockpick.data.universe import build_ticker_history_rows, detect_overlaps


def test_active_row_open_valid_to() -> None:
    rows = build_ticker_history_rows(
        [(1, "AAPL", "0000320193", date(1980, 12, 12), None)], {}
    )
    assert rows == [(1, "AAPL", "0000320193", date(1980, 12, 12), None)]


def test_delisted_row_valid_to_is_delisted_plus_one() -> None:
    # 폐지 마지막 실거래일=2010-01-01 → valid_to=2010-01-02(첫 무효일·배타 상한·경계 정렬).
    rows = build_ticker_history_rows(
        [(2, "DEAD", "0000000003", date(2000, 1, 1), date(2010, 1, 1))], {}
    )
    assert rows == [(2, "DEAD", "0000000003", date(2000, 1, 1), date(2010, 1, 2))]


def test_delisted_null_cik_recovered_from_a1() -> None:
    # stock.cik NULL + A1 복구맵에 있음 → 복구 cik 채택.
    rows = build_ticker_history_rows(
        [(3, "ENRNQ", None, date(1990, 1, 1), date(2001, 12, 2))],
        {"ENRNQ": ("0001024401", date(2001, 12, 2))},
    )
    assert rows == [(3, "ENRNQ", "0001024401", date(1990, 1, 1), date(2001, 12, 3))]


def test_delisted_null_cik_not_recovered_still_emits_window() -> None:
    # cik 미복구여도 윈도우 유지(cik=None) — 누락 시 재사용 과거가 미래 cik 누설(BLOCKING).
    rows = build_ticker_history_rows(
        [(4, "GHOST", None, date(2000, 1, 1), date(2005, 6, 1))], {}
    )
    assert rows == [(4, "GHOST", None, date(2000, 1, 1), date(2005, 6, 2))]


def test_null_listed_at_skipped() -> None:
    # 무가격 마스터 종목(listed_at None) → 거래 윈도우 없음·제외(MasterUniverse 정렬).
    assert build_ticker_history_rows([(5, "NOPX", "0000000007", None, None)], {}) == []


def test_degenerate_listed_ge_delisted_skipped() -> None:
    # listed≥delisted(하루도 거래 불가) → 제외(MasterUniverse degenerate 정렬).
    assert (
        build_ticker_history_rows(
            [(6, "DEGEN", "0000000008", date(2010, 1, 5), date(2010, 1, 5))], {}
        )
        == []
    )


def test_reuse_ticker_two_nonoverlapping_rows() -> None:
    # ticker RUSE 재사용: 엔티티1 폐지[2000~2010]·엔티티2 현재[2015~] → stock_id 당 1행·2행.
    rows = build_ticker_history_rows(
        [
            (7, "RUSE", "0000000001", date(2000, 1, 1), date(2010, 1, 1)),
            (8, "RUSE", "0000000002", date(2015, 1, 1), None),
        ],
        {},
    )
    assert rows == [
        (7, "RUSE", "0000000001", date(2000, 1, 1), date(2010, 1, 2)),
        (8, "RUSE", "0000000002", date(2015, 1, 1), None),
    ]
    assert detect_overlaps(rows) == []  # 비중첩 — 무결성 OK


def test_detect_overlaps_flags_overlapping_windows() -> None:
    # 추정 폐지일 오차로 윈도우 중첩(2010~2012) → 탐지(resolver 가 raise 할 무결성 위반·관측성).
    rows = [
        (9, "OVLP", "0000000004", date(2000, 1, 1), date(2012, 1, 1)),
        (10, "OVLP", "0000000005", date(2010, 1, 1), None),
    ]
    assert detect_overlaps(rows) == ["OVLP"]


def test_detect_overlaps_empty_when_clean() -> None:
    rows = [
        (1, "A", "c1", date(2000, 1, 1), date(2005, 1, 1)),
        (2, "B", "c2", date(2000, 1, 1), None),
    ]
    assert detect_overlaps(rows) == []
