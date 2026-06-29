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
) -> FinancialFact:
    return FinancialFact(cik, concept, fp, date(*period_end), date(*filed), Decimal(val))


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


def test_verify_detects_duplicate_natural_key(tmp_path: Path) -> None:
    dup = _fact("0000000001", "NetIncomeLoss", "2024-FY", (2024, 12, 31), (2025, 1, 15), "200")
    write_financial_facts([dup, dup], tmp_path, source="sec-edgar", ingested_at=_STAMP)
    report = verify_financial_facts(tmp_path)
    assert report.duplicate_count >= 1
    assert not report.passed


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
