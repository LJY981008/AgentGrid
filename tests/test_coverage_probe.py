"""A4 재무 커버리지 probe — fold별 ROE 산출율·결측 4분류·MNAR(라이브 0·결정적).

결측 4분류: 폐지-cik미해소 / 비신고-cik미해소 / cik해소-facts없음 / facts있음-ROE불가.
MNAR = top-decile 재무율 / 전체(B 하드필터 생존자-틸트 진단).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from stockpick.backtest.coverage_probe import (
    probe_coverage,
    probe_multimatch,
    probe_survivors,
)
from stockpick.types import FinancialFact


class _FakeUniverse:
    def __init__(self, members: set[str], delisted: dict[str, date]) -> None:
        self._members = members
        self._delisted = delisted

    def constituents(self, *, as_of: date) -> set[str]:  # noqa: ARG002
        return set(self._members)

    def delisting_event(self, ticker: str) -> date | None:
        return self._delisted.get(ticker)

    def ticker_count(self) -> int:
        return len(self._members)


class _FakeResolver:
    def __init__(self, cik_map: dict[str, str]) -> None:
        self._cik = cik_map

    def cik_for(self, ticker: str, *, on: date) -> str:  # noqa: ARG002
        return self._cik.get(ticker, "")


def _fact(cik: str, concept: str, val: str) -> FinancialFact:
    return FinancialFact(
        cik, concept, "2019-FY", date(2019, 12, 31), date(2020, 2, 1), Decimal(val)
    )


def _scenario() -> tuple[_FakeUniverse, _FakeResolver, list[FinancialFact]]:
    members = {"COVERED", "DELISTED_NOCIK", "ACTIVE_NOCIK", "FACTS_GAP", "ROE_GAP"}
    universe = _FakeUniverse(members, {"DELISTED_NOCIK": date(2018, 1, 1)})
    resolver = _FakeResolver(
        {"COVERED": "0000000001", "FACTS_GAP": "0000000004", "ROE_GAP": "0000000005"}
        # DELISTED_NOCIK·ACTIVE_NOCIK → cik 미해소("")
    )
    facts = [
        _fact("0000000001", "StockholdersEquity", "1000"),
        _fact("0000000001", "NetIncomeLoss", "200"),  # COVERED ROE=0.2
        _fact("0000000005", "StockholdersEquity", "0"),  # ROE_GAP equity<=0 → ROE None
        _fact("0000000005", "NetIncomeLoss", "50"),
        # 0000000004(FACTS_GAP) → facts 전무
    ]
    return universe, resolver, facts


def test_probe_classifies_missing_four_ways() -> None:
    universe, resolver, facts = _scenario()
    report = probe_coverage(
        [date(2020, 6, 1)], universe=universe, identity=resolver, facts=facts
    )
    assert len(report.folds) == 1
    f = report.folds[0]
    assert f.members == 5
    assert f.roe_computable == 1  # COVERED 만
    assert f.coverage_rate == 0.2
    assert f.missing_cik_delisted == 1  # DELISTED_NOCIK
    assert f.missing_cik_nonfiler == 1  # ACTIVE_NOCIK
    assert f.missing_facts == 1  # FACTS_GAP(cik 해소·facts 0)
    assert f.missing_roe == 1  # ROE_GAP(facts 있으나 equity<=0)


def test_probe_overall_rate_and_mnar() -> None:
    universe, resolver, facts = _scenario()
    report = probe_coverage(
        [date(2020, 6, 1)],
        universe=universe,
        identity=resolver,
        facts=facts,
        top_decile_by_as_of={date(2020, 6, 1): {"COVERED", "DELISTED_NOCIK"}},
    )
    assert report.overall_rate == pytest.approx(0.2)
    # top-decile{COVERED(ROE), DELISTED_NOCIK(미해소)} → top 재무율 0.5
    assert report.folds[0].top_decile_rate == 0.5
    assert report.mnar_skew == pytest.approx(2.5)  # 0.5 / 0.2 (top 과대커버 — 합성)


def test_probe_no_top_decile_mnar_none() -> None:
    universe, resolver, facts = _scenario()
    report = probe_coverage(
        [date(2020, 6, 1)], universe=universe, identity=resolver, facts=facts
    )
    assert report.mnar_skew is None
    assert report.folds[0].top_decile_rate is None


def test_probe_empty_members_zero_rate() -> None:
    universe = _FakeUniverse(set(), {})
    report = probe_coverage(
        [date(2020, 6, 1)], universe=universe, identity=_FakeResolver({}), facts=[]
    )
    assert report.folds[0].members == 0
    assert report.folds[0].coverage_rate == 0.0
    assert report.overall_rate == 0.0


# ── P4 (b)(a): probe_survivors / probe_multimatch ───────────────────────────


class _RaisingResolver:
    """다중매칭 ticker 는 ValueError(PitIdentity 계열)·그 외 맵(미해소="")."""

    def __init__(self, cik_map: dict[str, str], *, ambiguous: set[str]) -> None:
        self._cik = cik_map
        self._ambiguous = ambiguous

    def cik_for(self, ticker: str, *, on: date) -> str:  # noqa: ARG002
        if ticker in self._ambiguous:
            msg = f"다중매칭: {ticker}"
            raise ValueError(msg)
        return self._cik.get(ticker, "")


def test_probe_survivors_counts_profitable_only() -> None:
    # 생존 = filter_by_roe 통과(흑자·PIT) — COVERED(ROE 0.2) 만. ROE_GAP(equity0)·미해소·facts0 배제.
    universe, resolver, facts = _scenario()
    folds = probe_survivors(
        [date(2020, 6, 1)],
        universe=universe,
        identity=resolver,
        facts=facts,
        min_roe=Decimal("0"),
        max_age_days=None,
    )
    assert len(folds) == 1
    assert folds[0].members == 5
    assert folds[0].survivors == 1  # COVERED 만 흑자 생존
    assert folds[0].survivor_rate == pytest.approx(0.2)


def test_probe_survivors_min_roe_threshold() -> None:
    # min_roe 상향(0.5)이면 COVERED(0.2)도 탈락 → 생존 0(측정만·R1).
    universe, resolver, facts = _scenario()
    folds = probe_survivors(
        [date(2020, 6, 1)],
        universe=universe,
        identity=resolver,
        facts=facts,
        min_roe=Decimal("0.5"),
        max_age_days=None,
    )
    assert folds[0].survivors == 0


def test_probe_multimatch_counts_ambiguous_and_resolution() -> None:
    # DELISTED_NOCIK 를 다중매칭으로 강제 → multimatch 1. resolved 3(cik 있음)·unresolved 1(ACTIVE_NOCIK).
    members = {"COVERED", "DELISTED_NOCIK", "ACTIVE_NOCIK", "FACTS_GAP", "ROE_GAP"}
    universe = _FakeUniverse(members, {"DELISTED_NOCIK": date(2018, 1, 1)})
    resolver = _RaisingResolver(
        {"COVERED": "0000000001", "FACTS_GAP": "0000000004", "ROE_GAP": "0000000005"},
        ambiguous={"DELISTED_NOCIK"},
    )
    folds = probe_multimatch([date(2020, 6, 1)], universe=universe, identity=resolver)
    assert len(folds) == 1
    mf = folds[0]
    assert mf.members == 5
    assert mf.multimatch == 1  # DELISTED_NOCIK 모호식별
    assert mf.resolved == 3  # COVERED·FACTS_GAP·ROE_GAP
    assert mf.unresolved == 1  # ACTIVE_NOCIK("")


def test_probe_multimatch_zero_when_clean() -> None:
    universe, resolver, facts = _scenario()  # _FakeResolver 는 raise 안 함
    folds = probe_multimatch([date(2020, 6, 1)], universe=universe, identity=resolver)
    assert folds[0].multimatch == 0
    assert folds[0].resolved == 3
    assert folds[0].unresolved == 2
