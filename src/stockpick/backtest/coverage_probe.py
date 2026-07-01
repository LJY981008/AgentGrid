"""A4 재무 커버리지 probe — fold(as_of)별 ROE 산출가능 비율 + 결측 4분류 + MNAR skew.

다팩터 결합(Sub-project B) 착수 전 **측정가능성 게이트**의 입력. 깨끗한 momentum 게이트가 무알파로
fail 한 뒤(§4.1), 재무 결합이 의미 있으려면 임의 시점·임의 종목의 ROE/P/B 를 **충분한 커버리지**로
얻을 수 있어야 한다. 이 probe 가 fold 별 재무율을 측정해 B 의 G-5c 임계 입력·재무율 0%면 no-go.

ROE 산출 = cik 해소(`PitIdentityResolver`) ∧ facts 존재(`load_financial_facts`) ∧ (equity>0 ∧
net_income)(`financial_factors`). 결측 4분류로 "왜 못 구하나"를 명시(조용한 생존편향 금지):
  - 폐지-cik미해소: 폐지경계 있는데 cik 미해소(A1 매핑 갭).
  - 비신고-cik미해소: 비폐지인데 cik 미해소(ETF·외국·비신고사).
  - cik해소-facts없음: cik 해소됐으나 financial_fact 0(백필 미수집 또는 fy<2009 inert).
  - facts있음-ROE불가: facts 존재하나 ROE None(concept 결측·equity<=0·as_of 이전 공시).
MNAR skew = mean(top-decile momentum 재무율) / 전체 재무율 — top 이 체계적으로 다르면 B 하드필터가
재무NULL을 구조적으로 배제할 때 생존자-틸트(결측 무작위 아님). 라이브 0·결정적.

모듈 경계: `backtest`(상위 조합) — `rules.factors`·`ports`·`..types` 의존(engine/adapters 와 동일).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..rules.factors import financial_factors

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import date
    from decimal import Decimal

    from ..types import FinancialFact
    from .ports import IdentityResolver, UniversePort

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FoldCoverage:
    """한 as_of(fold)의 재무 커버리지 + 결측 4분류. 합계 members = roe_computable + 결측 4종."""

    as_of: date
    members: int
    roe_computable: int
    coverage_rate: float
    missing_cik_delisted: int  # 폐지경계 있음·cik 미해소(A1 매핑 갭)
    missing_cik_nonfiler: int  # 비폐지·cik 미해소(ETF·외국·비신고)
    missing_facts: int  # cik 해소·financial_fact 0(미수집 or fy<2009 inert)
    missing_roe: int  # facts 있음·ROE None(concept 결측·equity<=0·as_of 이전)
    top_decile_rate: float | None  # MNAR — top-decile 재무율(top 미제공 시 None)


@dataclass(frozen=True, slots=True)
class CoverageProbeReport:
    """probe 종합 — fold별 + 전체 재무율 + MNAR skew(B G-5c·go/no-go 입력)."""

    folds: tuple[FoldCoverage, ...]
    overall_rate: float
    mnar_skew: float | None


def probe_coverage(
    as_of_dates: Sequence[date],
    *,
    universe: UniversePort,
    identity: IdentityResolver,
    facts: list[FinancialFact],
    top_decile_by_as_of: Mapping[date, set[str]] | None = None,
) -> CoverageProbeReport:
    """fold별 ROE 산출율 + 결측 4분류 + MNAR. 순수(라이브 0·결정적). 상세=모듈 docstring."""
    # cik 인덱싱(성능 BLOCKING): financial_factors/latest_as_of 는 cik 필터로 전체 facts 선형스캔 →
    # 순진 호출은 O(resolved_ciks × 전체 facts)/fold(만-cik×수십만 facts = 타임아웃). cik 별 facts
    # 부분집합으로만 산출하면 O(전체 facts)/fold. (결과 불변 — 같은 latest_as_of 선택.)
    facts_by_cik: dict[str, list[FinancialFact]] = {}
    for fact in facts:
        facts_by_cik.setdefault(fact.cik, []).append(fact)
    facts_ciks = set(facts_by_cik)
    folds: list[FoldCoverage] = []
    total_members = 0
    total_roe = 0
    top_rates: list[float] = []
    for as_of in as_of_dates:
        members = sorted(universe.constituents(as_of=as_of))
        cik_of = {ticker: identity.cik_for(ticker, on=as_of) for ticker in members}
        resolved_ciks = {cik for cik in cik_of.values() if cik}
        roe_ciks = {
            cik
            for cik in resolved_ciks & facts_ciks
            if financial_factors(facts_by_cik[cik], ciks=(cik,), as_of=as_of)[cik].roe is not None
        }

        roe_computable = miss_del = miss_non = miss_facts = miss_roe = 0
        for ticker in members:
            cik = cik_of[ticker]
            if not cik:
                if universe.delisting_event(ticker) is not None:
                    miss_del += 1  # 폐지·cik 미해소
                else:
                    miss_non += 1  # 비폐지·cik 미해소(비신고)
            elif cik not in facts_ciks:
                miss_facts += 1  # cik 해소·facts 0
            elif cik not in roe_ciks:
                miss_roe += 1  # facts 있음·ROE 산출 불가
            else:
                roe_computable += 1
        rate = roe_computable / len(members) if members else 0.0

        top_rate: float | None = None
        if top_decile_by_as_of is not None:
            top = top_decile_by_as_of.get(as_of, set()) & set(members)
            if top:
                top_hit = sum(1 for t in top if cik_of[t] and cik_of[t] in roe_ciks)
                top_rate = top_hit / len(top)
                top_rates.append(top_rate)

        folds.append(
            FoldCoverage(
                as_of=as_of,
                members=len(members),
                roe_computable=roe_computable,
                coverage_rate=rate,
                missing_cik_delisted=miss_del,
                missing_cik_nonfiler=miss_non,
                missing_facts=miss_facts,
                missing_roe=miss_roe,
                top_decile_rate=top_rate,
            )
        )
        total_members += len(members)
        total_roe += roe_computable

    overall_rate = total_roe / total_members if total_members else 0.0
    mnar_skew: float | None = None
    if top_rates and overall_rate > 0:
        mnar_skew = (sum(top_rates) / len(top_rates)) / overall_rate
    logger.info(
        "커버리지 probe: fold=%d, 전체 재무율=%.4f, MNAR=%s", len(folds), overall_rate, mnar_skew
    )
    return CoverageProbeReport(folds=tuple(folds), overall_rate=overall_rate, mnar_skew=mnar_skew)


@dataclass(frozen=True, slots=True)
class SurvivorFold:
    """한 as_of 흑자 생존수 — filter_by_roe(게이트와 동일) 통과 종목 수·비율(B G-5c 생존수 입력)."""

    as_of: date
    members: int
    survivors: int
    survivor_rate: float


def probe_survivors(
    as_of_dates: Sequence[date],
    *,
    universe: UniversePort,
    identity: IdentityResolver,
    facts: list[FinancialFact],
    min_roe: Decimal,
    max_age_days: int | None,
) -> tuple[SurvivorFold, ...]:
    """as_of별 흑자 생존수 — 게이트 `filter_by_roe` 와 **동일 의미**(ROE>min_roe·PIT·recency).

    커버리지(probe_coverage=ROE 산출가능)와 구분: survivor = 산출가능 ∧ 흑자(하드필터 실제 통과분).
    소수 생존이면 분산 붕괴·과최적화 위험(측정만·임계 미조정·R1). filter_by_roe 공유로 게이트 정합.
    """
    from .engine import filter_by_roe

    folds: list[SurvivorFold] = []
    for as_of in as_of_dates:
        members = universe.constituents(as_of=as_of)
        survivors = filter_by_roe(
            members,
            identity=identity,
            financial_facts=facts,
            as_of=as_of,
            min_roe=min_roe,
            max_age_days=max_age_days,
        )
        rate = len(survivors) / len(members) if members else 0.0
        folds.append(
            SurvivorFold(
                as_of=as_of,
                members=len(members),
                survivors=len(survivors),
                survivor_rate=rate,
            )
        )
    return tuple(folds)


@dataclass(frozen=True, slots=True)
class MultiMatchFold:
    """한 as_of ticker→cik 무결성 — 다중매칭(ValueError)·미해소·해소 수(G-7 pre-flight)."""

    as_of: date
    members: int
    resolved: int
    unresolved: int
    multimatch: int


def probe_multimatch(
    as_of_dates: Sequence[date],
    *,
    universe: UniversePort,
    identity: IdentityResolver,
) -> tuple[MultiMatchFold, ...]:
    """as_of별 ticker→cik 다중매칭(ValueError) 실측 — filter_by_roe 가 배제하는 모호식별 규모.

    PitIdentityResolver 는 ticker_history 다중매칭 시 raise(BLOCKING) → 게이트/필터가 그 종목을
    조용히 배제. 다수 fold 대량이면 유니버스 신뢰 저하(pre-flight G-7 계열·측정만·no-go 입력·R1).
    """
    folds: list[MultiMatchFold] = []
    for as_of in as_of_dates:
        members = sorted(universe.constituents(as_of=as_of))
        resolved = unresolved = multimatch = 0
        for ticker in members:
            try:
                cik = identity.cik_for(ticker, on=as_of)
            except ValueError:  # ticker_history 다중매칭 = 모호식별(filter_by_roe 배제 대상)
                multimatch += 1
                continue
            if cik:
                resolved += 1
            else:
                unresolved += 1
        folds.append(
            MultiMatchFold(
                as_of=as_of,
                members=len(members),
                resolved=resolved,
                unresolved=unresolved,
                multimatch=multimatch,
            )
        )
    return tuple(folds)


def main() -> int:
    """`python -m stockpick.backtest.coverage_probe` — 정지점3 RUN(실 백필 데이터 후).

    연도별 as_of(6/30·2010~2025)에 MasterUniverse·PitIdentityResolver·재무 fact 로 커버리지 측정.
    MNAR(top-decile)은 momentum 결선 필요 → v1 미포함(coverage 분류가 go/no-go 1차 입력). 읽기전용.
    """
    import argparse
    import logging as _logging
    import os
    from datetime import date
    from decimal import Decimal
    from pathlib import Path

    from ..rules._financials import load_financial_facts
    from .adapters import MasterUniverse
    from .identity import PitIdentityResolver

    _logging.basicConfig(level=_logging.INFO)
    parser = argparse.ArgumentParser(prog="stockpick.backtest.coverage_probe")
    parser.add_argument(
        "--factor",
        action="store_true",
        help="B dry-run — 흑자 생존수(probe_survivors)·다중매칭(probe_multimatch) 추가 측정",
    )
    parser.add_argument("--min-roe", type=str, default="0", help="흑자 하한(ROE>min·기본 0)")
    parser.add_argument(
        "--max-age-days", type=int, default=None, help="재무 recency 상한(일·기본 무제한)"
    )
    args = parser.parse_args()

    base_dir = Path(os.environ.get("STOCKPICK_DATA_DIR", "data/parquet"))
    universe = MasterUniverse(base_dir)
    identity = PitIdentityResolver(base_dir)
    facts = load_financial_facts(base_dir)
    as_of_dates = [date(year, 6, 30) for year in range(2010, 2026)]
    report = probe_coverage(as_of_dates, universe=universe, identity=identity, facts=facts)

    print(  # noqa: T201 — 진입점 출력
        f"[probe] 재무 커버리지 — 전체 ROE 산출율 {report.overall_rate:.2%} (fact {len(facts):,}건)"
    )
    print("  as_of      members   ROE   rate  | 폐지 비신고 facts0 ROE불가")  # noqa: T201
    for fold in report.folds:
        print(  # noqa: T201
            f"  {fold.as_of} {fold.members:>7} {fold.roe_computable:>5} "
            f"{fold.coverage_rate:>5.1%}  | {fold.missing_cik_delisted:>4} "
            f"{fold.missing_cik_nonfiler:>5} {fold.missing_facts:>5} {fold.missing_roe:>6}"
        )

    if args.factor:
        # (a) 흑자 생존수 — 게이트 filter_by_roe 와 동일 의미(ROE>min·PIT·recency). R1 임계 미조정.
        surv = probe_survivors(
            as_of_dates,
            universe=universe,
            identity=identity,
            facts=facts,
            min_roe=Decimal(args.min_roe),
            max_age_days=args.max_age_days,
        )
        print(  # noqa: T201
            f"[probe] 흑자 생존수(min_roe>{args.min_roe}·max_age={args.max_age_days})"
        )
        print("  as_of      members  survivors  rate")  # noqa: T201
        for sf in surv:
            print(  # noqa: T201
                f"  {sf.as_of} {sf.members:>7} {sf.survivors:>9} {sf.survivor_rate:>6.1%}"
            )
        # (b) ticker→cik 다중매칭 실측(pre-flight G-7 계열) — filter_by_roe 조용 배제 규모.
        mm = probe_multimatch(as_of_dates, universe=universe, identity=identity)
        total_mm = sum(f.multimatch for f in mm)
        print(f"[probe] 다중매칭(ValueError) 총 {total_mm}건 / fold")  # noqa: T201
        print("  as_of      members  resolved  unresolved  multimatch")  # noqa: T201
        for mf in mm:
            print(  # noqa: T201
                f"  {mf.as_of} {mf.members:>7} {mf.resolved:>9} "
                f"{mf.unresolved:>11} {mf.multimatch:>11}"
            )
        # (c) MNAR: top-decile 재무율/전체(probe_coverage top_decile_rate) — top-decile 은 momentum
        # 결선(price port·OOM 위험) 필요. 유니버스 레벨 커버는 위 표, top-decile MNAR 는 게이트 G-5c
        # 경로(_measure_g5c)·별도 momentum 결선서 측정(여기선 미결선·측정 안전 우선).
        print(  # noqa: T201
            "[probe] MNAR(top-decile 후속수익 skew)는 momentum 결선 필요 → 게이트 G-5c 경로서 측정"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
