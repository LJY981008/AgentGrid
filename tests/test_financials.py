"""재무 PIT 접근(rules/_financials) — 합성 fact·라이브 0.

핵심 = 룩어헤드 BLOCKING(재무): disclosed_at(filed)<=as_of 만, period_end(end) 기준 아님.
test_latest_as_of_excludes_future_disclosure_lookahead 가 미래 공시 누설 회귀를 봉인한다.
그 외: 회계기간 최신 선택·정정공시(amendment) 최신·annual_only 분기제외·미해소 None·로드 위임.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from stockpick.data.edgar import store_financials
from stockpick.rules._financials import latest_as_of, load_financial_facts
from stockpick.types import FinancialFact

_CIK = "0000320193"


def _fact(
    concept: str,
    fiscal_period: str,
    period_end: tuple[int, int, int],
    disclosed_at: tuple[int, int, int],
    value: str,
    *,
    cik: str = _CIK,
) -> FinancialFact:
    return FinancialFact(
        cik=cik,
        concept=concept,
        fiscal_period=fiscal_period,
        period_end=date(*period_end),
        disclosed_at=date(*disclosed_at),
        value=Decimal(value),
    )


def test_latest_as_of_picks_latest_period() -> None:
    facts = [
        _fact("StockholdersEquity", "2022-FY", (2022, 9, 24), (2022, 10, 28), "50"),
        _fact("StockholdersEquity", "2023-FY", (2023, 9, 30), (2023, 11, 3), "62"),
        _fact("StockholdersEquity", "2024-FY", (2024, 9, 28), (2024, 11, 1), "57"),
    ]
    sel = latest_as_of(facts, concept="StockholdersEquity", cik=_CIK, as_of=date(2025, 1, 1))
    assert sel is not None
    assert sel.fiscal_period == "2024-FY"
    assert sel.value == Decimal("57")


def test_latest_as_of_excludes_future_disclosure_lookahead() -> None:
    # 룩어헤드 BLOCKING: 2024-FY 회계기간말(2024-09-28)은 as_of(2024-10-15) 이전이나
    # 공시일(filed 2024-11-01)은 as_of 이후 → as_of 시점엔 미공시 → 제외하고 2023-FY 선택.
    facts = [
        _fact("StockholdersEquity", "2023-FY", (2023, 9, 30), (2023, 11, 3), "62"),
        _fact("StockholdersEquity", "2024-FY", (2024, 9, 28), (2024, 11, 1), "57"),
    ]
    sel = latest_as_of(facts, concept="StockholdersEquity", cik=_CIK, as_of=date(2024, 10, 15))
    assert sel is not None
    assert sel.fiscal_period == "2023-FY"  # 미래 공시 누설 차단(period_end 아니라 filed 기준)


def test_latest_as_of_amendment_prefers_later_disclosure() -> None:
    # 같은 회계기간(2023-FY) 원본·정정(10-K/A): period_end 동일 → disclosed_at 늦은 정정값 사용.
    facts = [
        _fact("NetIncomeLoss", "2023-FY", (2023, 9, 30), (2023, 11, 3), "97000"),
        _fact("NetIncomeLoss", "2023-FY", (2023, 9, 30), (2024, 2, 1), "96995"),
    ]
    sel = latest_as_of(facts, concept="NetIncomeLoss", cik=_CIK, as_of=date(2024, 6, 1))
    assert sel is not None
    assert sel.value == Decimal("96995")


def test_latest_as_of_annual_only_excludes_quarterly() -> None:
    facts = [
        _fact("NetIncomeLoss", "2024-FY", (2024, 9, 28), (2024, 11, 1), "93736"),
        _fact("NetIncomeLoss", "2025-Q1", (2024, 12, 28), (2025, 1, 30), "20000"),
    ]
    annual = latest_as_of(
        facts, concept="NetIncomeLoss", cik=_CIK, as_of=date(2025, 3, 1), annual_only=True
    )
    assert annual is not None
    assert annual.fiscal_period == "2024-FY"  # 분기 제외
    latest = latest_as_of(facts, concept="NetIncomeLoss", cik=_CIK, as_of=date(2025, 3, 1))
    assert latest is not None
    assert latest.fiscal_period == "2025-Q1"  # annual_only=False 면 분기 포함 최신


def test_latest_as_of_none_before_any_disclosure() -> None:
    facts = [_fact("StockholdersEquity", "2024-FY", (2024, 9, 28), (2024, 11, 1), "57")]
    assert (
        latest_as_of(facts, concept="StockholdersEquity", cik=_CIK, as_of=date(2024, 1, 1)) is None
    )


def test_latest_as_of_none_for_unknown_cik_or_concept() -> None:
    facts = [_fact("StockholdersEquity", "2024-FY", (2024, 9, 28), (2024, 11, 1), "57")]
    assert (
        latest_as_of(facts, concept="StockholdersEquity", cik="9999999999", as_of=date(2025, 1, 1))
        is None
    )
    assert latest_as_of(facts, concept="Assets", cik=_CIK, as_of=date(2025, 1, 1)) is None


def test_load_financial_facts_delegates(tmp_path: Path) -> None:
    facts = [_fact("StockholdersEquity", "2024-FY", (2024, 9, 28), (2024, 11, 1), "57")]
    store_financials(facts, tmp_path)
    assert load_financial_facts(tmp_path) == facts


def test_load_financial_facts_missing_empty(tmp_path: Path) -> None:
    assert load_financial_facts(tmp_path) == []


def test_load_financial_facts_parquet_precedence_over_json(tmp_path: Path) -> None:
    # A3: Parquet 백필본이 있으면 그걸 우선(구 JSON 폴백은 미적재 때만). latest_as_of 불변.
    from datetime import UTC, datetime

    from stockpick.data.storage import write_financial_facts

    write_financial_facts(
        [_fact("StockholdersEquity", "2024-FY", (2024, 9, 28), (2024, 11, 1), "999")],
        tmp_path,
        source="sec-edgar",
        ingested_at=datetime(2026, 6, 29, tzinfo=UTC),
    )
    store_financials(  # JSON 도 존재하나 Parquet 우선 → 무시
        [_fact("StockholdersEquity", "2024-FY", (2024, 9, 28), (2024, 11, 1), "1")], tmp_path
    )
    loaded = load_financial_facts(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].value == Decimal("999")  # Parquet 값(JSON 1 아님)
