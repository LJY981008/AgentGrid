"""재무 팩터(rules/factors.financial_factors) — 합성 fact·라이브 0.

검증: ROE=NetIncome/Equity·P/B=price*shares/equity 정확값·적자 음 ROE·분모<=0 None·
가격/주식수 결측 시 P/B None(ROE 보존)·미해소 cik 전부 None 보존·룩어헤드(미래 공시 제외).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from stockpick.rules.factors import financial_factors
from stockpick.types import FinancialFact

_CIK = "0000000001"


def _fact(concept: str, period: str, value: str, *, filed: tuple[int, int, int]) -> FinancialFact:
    # period "2024-FY" → period_end = 그 회계연도 말(12/31 단순화), filed = 인자.
    year = int(period.split("-")[0])
    return FinancialFact(
        cik=_CIK,
        concept=concept,
        fiscal_period=period,
        period_end=date(year, 12, 31),
        disclosed_at=date(*filed),
        value=Decimal(value),
    )


def _full_facts() -> list[FinancialFact]:
    return [
        _fact("StockholdersEquity", "2024-FY", "1000", filed=(2025, 2, 1)),
        _fact("NetIncomeLoss", "2024-FY", "200", filed=(2025, 2, 1)),
        _fact("EntityCommonStockSharesOutstanding", "2024-FY", "100", filed=(2025, 2, 1)),
    ]


def test_financial_factors_roe_and_pb() -> None:
    scores = financial_factors(
        _full_facts(), ciks=[_CIK], as_of=date(2025, 3, 1), price_by_cik={_CIK: Decimal("25")}
    )
    s = scores[_CIK]
    assert s.roe == Decimal("0.2")  # 200 / 1000
    assert s.pb == Decimal("2.5")  # price 25 * shares 100 / equity 1000 = 2500/1000
    assert s.equity == Decimal("1000")
    assert s.shares == Decimal("100")
    assert s.equity_period == "2024-FY"
    assert s.net_income_period == "2024-FY"


def test_financial_factors_negative_net_income_negative_roe() -> None:
    facts = [
        _fact("StockholdersEquity", "2024-FY", "1000", filed=(2025, 2, 1)),
        _fact("NetIncomeLoss", "2024-FY", "-50", filed=(2025, 2, 1)),
    ]
    s = financial_factors(facts, ciks=[_CIK], as_of=date(2025, 3, 1))[_CIK]
    assert s.roe == Decimal("-0.05")  # 적자 = 음 ROE(실제 신호 — 추측·클램프 금지)
    assert s.pb is None  # shares·price 결측


def test_financial_factors_nonpositive_equity_none() -> None:
    facts = [
        _fact("StockholdersEquity", "2024-FY", "0", filed=(2025, 2, 1)),
        _fact("NetIncomeLoss", "2024-FY", "200", filed=(2025, 2, 1)),
        _fact("EntityCommonStockSharesOutstanding", "2024-FY", "100", filed=(2025, 2, 1)),
    ]
    s = financial_factors(
        facts, ciks=[_CIK], as_of=date(2025, 3, 1), price_by_cik={_CIK: Decimal("25")}
    )[_CIK]
    assert s.roe is None  # 0 분모 — 조용한 0 division 금지
    assert s.pb is None


def test_financial_factors_fy_mismatch_no_roe() -> None:
    # H8: equity 최신=FY2024·income 최신=FY2023 → 다른 FY → ROE None(왜곡 방지).
    facts = [
        _fact("StockholdersEquity", "2024-FY", "1000", filed=(2025, 2, 1)),
        _fact("StockholdersEquity", "2023-FY", "900", filed=(2024, 2, 1)),
        _fact("NetIncomeLoss", "2023-FY", "180", filed=(2024, 2, 1)),  # income 최신=FY2023
    ]
    s = financial_factors(facts, ciks=[_CIK], as_of=date(2025, 3, 1))[_CIK]
    assert s.roe is None  # equity FY2024 vs income FY2023 불일치 → ROE 미산출


def test_financial_factors_max_age_stale_no_roe() -> None:
    # H5: 4년 전 흑자만 있는 cik → max_age_days 초과 → equity/income stale 배제 → ROE None.
    facts = [
        _fact("StockholdersEquity", "2019-FY", "1000", filed=(2020, 2, 1)),
        _fact("NetIncomeLoss", "2019-FY", "200", filed=(2020, 2, 1)),
    ]
    s = financial_factors(facts, ciks=[_CIK], as_of=date(2024, 3, 1), max_age_days=548)[_CIK]
    assert s.roe is None  # stale(≈4년) 배제
    s2 = financial_factors(facts, ciks=[_CIK], as_of=date(2024, 3, 1))[_CIK]
    assert s2.roe == Decimal("0.2")  # max_age 없으면 산출(하위호환)


def test_financial_factors_missing_price_no_pb_but_roe() -> None:
    s = financial_factors(_full_facts(), ciks=[_CIK], as_of=date(2025, 3, 1))[_CIK]  # price 없음
    assert s.roe == Decimal("0.2")
    assert s.pb is None  # 가격 결측 → P/B 불가


def test_financial_factors_missing_shares_no_pb() -> None:
    facts = [
        _fact("StockholdersEquity", "2024-FY", "1000", filed=(2025, 2, 1)),
        _fact("NetIncomeLoss", "2024-FY", "200", filed=(2025, 2, 1)),
    ]
    s = financial_factors(
        facts, ciks=[_CIK], as_of=date(2025, 3, 1), price_by_cik={_CIK: Decimal("25")}
    )[_CIK]
    assert s.roe == Decimal("0.2")
    assert s.pb is None  # shares 결측


def test_financial_factors_unresolved_cik_present_all_none() -> None:
    scores = financial_factors([], ciks=["unknown"], as_of=date(2025, 3, 1))
    assert "unknown" in scores  # 조용한 누락 금지 — 맵에 남김
    s = scores["unknown"]
    assert s.roe is None
    assert s.pb is None
    assert s.equity is None


def test_financial_factors_lookahead_excludes_future_filing() -> None:
    # 2024-FY 회계기간말(2024-12-31)은 as_of(2025-01-15) 이전이나 공시(filed 2025-02-01)는 이후 →
    # as_of 시점엔 미공시 → 2023-FY 사용(미래 공시 누설 차단).
    facts = [
        _fact("StockholdersEquity", "2023-FY", "800", filed=(2024, 2, 1)),
        _fact("NetIncomeLoss", "2023-FY", "160", filed=(2024, 2, 1)),
        _fact("StockholdersEquity", "2024-FY", "1000", filed=(2025, 2, 1)),
        _fact("NetIncomeLoss", "2024-FY", "200", filed=(2025, 2, 1)),
    ]
    s = financial_factors(facts, ciks=[_CIK], as_of=date(2025, 1, 15))[_CIK]
    assert s.equity == Decimal("800")  # 2023-FY (2024-FY 미공시)
    assert s.roe == Decimal("0.2")  # 160 / 800
    assert s.equity_period == "2023-FY"
