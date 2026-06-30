"""financial_fact Parquet 저장/로드/검증(A3) — daily_bar 동형·라이브 0.

레이아웃 `financial_fact/cik=<CIK>/facts.parquet`(cik 파티션·증분 atomic·resume 친화). 음수 정당
(적자 NetIncomeLoss·음수 equity)·자연키(cik,concept,fiscal_period,disclosed_at) 중복=오염·정정공시
(같은 회계기간 다른 disclosed_at)=별행.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from stockpick.data.storage import (
    load_financial_facts,
    verify_financial_facts,
    write_financial_facts,
)
from stockpick.types import FinancialFact

_STAMP = datetime(2026, 6, 29, tzinfo=UTC)


def _fact(
    cik: str,
    concept: str,
    fp: str,
    period_end: tuple[int, int, int],
    filed: tuple[int, int, int],
    val: str,
    *,
    start: tuple[int, int, int] | None = None,
) -> FinancialFact:
    return FinancialFact(
        cik,
        concept,
        fp,
        date(*period_end),
        date(*filed),
        Decimal(val),
        period_start=date(*start) if start is not None else None,
    )


def test_write_load_roundtrip_preserves_fields_and_negative(tmp_path: Path) -> None:
    facts = [
        _fact("0000000001", "NetIncomeLoss", "2024-FY", (2024, 12, 31), (2025, 1, 15), "200"),
        _fact("0000000001", "StockholdersEquity", "2024-FY", (2024, 12, 31), (2025, 1, 15), "1000"),
        _fact("0000000002", "NetIncomeLoss", "2023-FY", (2023, 12, 31), (2024, 2, 1), "-50"),
    ]
    write_financial_facts(facts, tmp_path, source="sec-edgar", ingested_at=_STAMP)
    loaded = load_financial_facts(tmp_path)
    assert len(loaded) == 3
    by = {(f.cik, f.concept, f.fiscal_period): f for f in loaded}
    nil = by[("0000000001", "NetIncomeLoss", "2024-FY")]
    assert nil.value == Decimal("200")
    assert nil.period_end == date(2024, 12, 31)
    assert nil.disclosed_at == date(2025, 1, 15)
    assert by[("0000000002", "NetIncomeLoss", "2023-FY")].value == Decimal("-50")  # 음수 보존


def test_load_empty_when_absent(tmp_path: Path) -> None:
    assert load_financial_facts(tmp_path) == []


def test_write_per_cik_overwrite_idempotent(tmp_path: Path) -> None:
    # 같은 cik 재적재(resume 재시도) → 파티션 덮어쓰기·중복 0(companyfacts 는 cik 단위 완전 fetch).
    facts = [_fact("0000000001", "NetIncomeLoss", "2024-FY", (2024, 12, 31), (2025, 1, 15), "200")]
    write_financial_facts(facts, tmp_path, source="sec-edgar", ingested_at=_STAMP)
    write_financial_facts(facts, tmp_path, source="sec-edgar", ingested_at=_STAMP)
    assert len(load_financial_facts(tmp_path)) == 1


def test_write_empty_noop(tmp_path: Path) -> None:
    write_financial_facts([], tmp_path, source="sec-edgar", ingested_at=_STAMP)
    assert load_financial_facts(tmp_path) == []


def test_write_dedups_identical_natural_key(tmp_path: Path) -> None:
    # write 가 자연키 중복 제거 → 동일 fact 2개여도 1행(verify clean).
    dup = _fact("0000000001", "NetIncomeLoss", "2024-FY", (2024, 12, 31), (2025, 1, 15), "200",
                start=(2024, 1, 1))
    write_financial_facts([dup, dup], tmp_path, source="sec-edgar", ingested_at=_STAMP)
    assert len(load_financial_facts(tmp_path)) == 1
    assert verify_financial_facts(tmp_path).passed


def test_write_dedups_fy_label_keeps_annual(tmp_path: Path) -> None:
    # 같은 자연키·fy/fp 라벨만 다름(한 신고 FY/Q 2라벨) → 1행·"-FY"(annual canonical) 우선 보존.
    facts = [
        _fact("0000000001", "NetIncomeLoss", "2025-Q1", (2024, 12, 31), (2025, 2, 1), "200",
              start=(2024, 1, 1)),
        _fact("0000000001", "NetIncomeLoss", "2024-FY", (2024, 12, 31), (2025, 2, 1), "200",
              start=(2024, 1, 1)),
    ]
    write_financial_facts(facts, tmp_path, source="sec-edgar", ingested_at=_STAMP)
    loaded = load_financial_facts(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].fiscal_period == "2024-FY"  # 연간 라벨 보존(annual_only 인식)


def test_write_dedups_value_conflict_deterministic(tmp_path: Path) -> None:
    # 같은 자연키·다른 value(드문 동일신고 정정) → 1행 결정적(최대값).
    facts = [
        _fact("0000000001", "StockholdersEquity", "2024-FY", (2024, 12, 31), (2025, 2, 1), "100"),
        _fact("0000000001", "StockholdersEquity", "2024-FY", (2024, 12, 31), (2025, 2, 1), "200"),
    ]
    write_financial_facts(facts, tmp_path, source="sec-edgar", ingested_at=_STAMP)
    loaded = load_financial_facts(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].value == Decimal("200")  # 최대값(결정적)
    assert verify_financial_facts(tmp_path).passed


def test_verify_detects_corruption_bypassing_write(tmp_path: Path) -> None:
    # verify 무결성 게이트 — write dedup 우회(직접 같은 키 2행 적재)면 탐지.
    import pyarrow as pa
    import pyarrow.parquet as pq

    from stockpick.data.storage import _financial_arrow_schema

    rows = {
        "cik": ["0000000001", "0000000001"],
        "concept": ["StockholdersEquity", "StockholdersEquity"],
        "fiscal_period": ["2024-FY", "2024-FY"],
        "period_start": [None, None],
        "period_end": [date(2024, 12, 31), date(2024, 12, 31)],
        "disclosed_at": [date(2025, 2, 1), date(2025, 2, 1)],
        "value": [Decimal("100"), Decimal("200")],
        "source": ["x", "x"],
        "ingested_at": [_STAMP, _STAMP],
    }
    out = tmp_path / "financial_fact"
    out.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pydict(rows, schema=_financial_arrow_schema())
    pq.write_table(table, str(out / "x.parquet"))  # type: ignore[no-untyped-call]
    report = verify_financial_facts(tmp_path)
    assert report.duplicate_count == 1
    assert not report.passed


def test_verify_same_fiscal_period_diff_period_end_not_dup(tmp_path: Path) -> None:
    # 자연키=period_end(fy-fp 아님). 같은 fiscal_period라도 period_end 다르면 distinct.
    facts = [
        _fact("0000000001", "StockholdersEquity", "2011-Q1", (2010, 5, 31), (2010, 9, 23), "746"),
        _fact("0000000001", "StockholdersEquity", "2011-Q1", (2010, 8, 31), (2010, 9, 23), "760"),
    ]
    write_financial_facts(facts, tmp_path, source="sec-edgar", ingested_at=_STAMP)
    report = verify_financial_facts(tmp_path)
    assert report.row_count == 2
    assert report.duplicate_count == 0  # period_end 다름 → 중복 아님
    assert report.passed


def test_duration_same_end_diff_start_roundtrip_and_not_dup(tmp_path: Path) -> None:
    # NetIncomeLoss duration: 같은 end·다른 start(FY vs Q4) = distinct. period_start 왕복+비중복.
    facts = [
        _fact("0000000001", "NetIncomeLoss", "2010-Q2", (2008, 12, 31), (2010, 2, 8), "1623",
              start=(2008, 1, 1)),  # FY2008
        _fact("0000000001", "NetIncomeLoss", "2010-Q2", (2008, 12, 31), (2010, 2, 8), "578",
              start=(2008, 10, 1)),  # Q4 2008
    ]
    write_financial_facts(facts, tmp_path, source="sec-edgar", ingested_at=_STAMP)
    loaded = load_financial_facts(tmp_path)
    starts = sorted(str(f.period_start) for f in loaded)
    assert starts == ["2008-01-01", "2008-10-01"]  # period_start 왕복 보존
    report = verify_financial_facts(tmp_path)
    assert report.duplicate_count == 0  # start 다름 → 중복 아님
    assert report.passed


def test_verify_amendment_is_not_duplicate(tmp_path: Path) -> None:
    # 같은 (cik,concept,fiscal_period) 다른 disclosed_at = 정정공시 별행(중복 아님·passed).
    orig = _fact("0000000001", "NetIncomeLoss", "2024-FY", (2024, 12, 31), (2025, 1, 15), "200")
    amend = _fact("0000000001", "NetIncomeLoss", "2024-FY", (2024, 12, 31), (2025, 3, 1), "210")
    write_financial_facts([orig, amend], tmp_path, source="sec-edgar", ingested_at=_STAMP)
    report = verify_financial_facts(tmp_path)
    assert report.duplicate_count == 0
    assert report.passed
    assert report.row_count == 2
    assert report.cik_count == 1
