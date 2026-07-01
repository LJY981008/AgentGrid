"""B ROE 하드필터(backtest.engine.filter_by_roe + engine/benchmark 배선) — 합성·라이브 0.

방식 C(가중 0·하드필터)·**ROE→momentum 순서**·**off=momentum bit-identical(최우선 회귀)**·
벤치 대칭(H3)·룩어헤드/stale/자본잠식/다중매칭/미해소 명시 배제(중립채움 금지).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from stockpick.backtest.benchmark import equal_weight_universe
from stockpick.backtest.config import BacktestConfig
from stockpick.backtest.engine import filter_by_roe, run
from stockpick.backtest.fakes import (
    FakeLiquidityPort,
    FakePriceSeriesPort,
    FakeUniversePort,
    StubIdentityResolver,
)
from stockpick.backtest.strategy import EqualWeightTopN
from stockpick.rules._scan import PricePoint
from stockpick.types import FinancialFact


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _fact(
    cik: str, concept: str, fy: int, value: str, *, filed: tuple[int, int, int]
) -> FinancialFact:
    # fy → period_end = 그 회계연도 말(12/31 단순화). disclosed_at = filed(EDGAR).
    return FinancialFact(
        cik=cik,
        concept=concept,
        fiscal_period=f"{fy}-FY",
        period_end=date(fy, 12, 31),
        disclosed_at=date(*filed),
        value=Decimal(value),
    )


def _roe_facts(
    cik: str, *, fy: int, equity: str, net_income: str, filed: tuple[int, int, int]
) -> list[FinancialFact]:
    return [
        _fact(cik, "StockholdersEquity", fy, equity, filed=filed),
        _fact(cik, "NetIncomeLoss", fy, net_income, filed=filed),
    ]


class _MultiMatchResolver:
    """다중매칭 ticker 는 ValueError(PitIdentity 계열) — 그 외는 맵(미해소=빈 문자열)."""

    def __init__(self, mapping: dict[str, str], *, ambiguous: set[str]) -> None:
        self._mapping = mapping
        self._ambiguous = ambiguous

    def cik_for(self, ticker: str, *, on: date) -> str:  # noqa: ARG002 (골격 시변 무시)
        if ticker in self._ambiguous:
            msg = f"다중매칭: {ticker}"
            raise ValueError(msg)
        return self._mapping.get(ticker, "")


_AS_OF = date(2024, 6, 3)  # 모든 FY2022(filed 2023-03) 공시 이후·recency ~1.2년
# ROE 0.2 (흑자) / ROE -0.05 (적자)
_PROFIT = _roe_facts("CIK_A", fy=2022, equity="1000", net_income="200", filed=(2023, 3, 1))
_LOSS = _roe_facts("CIK_B", fy=2022, equity="1000", net_income="-50", filed=(2023, 3, 1))


# ── filter_by_roe 단위 ─────────────────────────────────────────────────────


def test_filter_keeps_profitable_drops_loss() -> None:
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    kept = filter_by_roe(
        {"A", "B"},
        identity=ident,
        financial_facts=[*_PROFIT, *_LOSS],
        as_of=_AS_OF,
        min_roe=Decimal(0),
        max_age_days=None,
    )
    assert kept == {"A"}  # A 흑자 보존·B 적자 배제


def test_filter_drops_missing_financials() -> None:
    # 재무 fact 아예 없는 cik → ROE 산출불가 → 배제(결측 명시 배제·중립채움 금지).
    ident = StubIdentityResolver({"A": "CIK_A", "C": "CIK_C"})
    kept = filter_by_roe(
        {"A", "C"}, identity=ident, financial_facts=list(_PROFIT),
        as_of=_AS_OF, min_roe=Decimal(0), max_age_days=None,
    )
    assert kept == {"A"}  # C 무재무 배제


def test_filter_drops_capital_impairment() -> None:
    # equity<=0(자본잠식) → ROE None → 배제(조용한 0-division 금지).
    impaired = _roe_facts("CIK_D", fy=2022, equity="0", net_income="200", filed=(2023, 3, 1))
    ident = StubIdentityResolver({"A": "CIK_A", "D": "CIK_D"})
    kept = filter_by_roe(
        {"A", "D"}, identity=ident, financial_facts=[*_PROFIT, *impaired],
        as_of=_AS_OF, min_roe=Decimal(0), max_age_days=None,
    )
    assert kept == {"A"}


def test_filter_min_roe_threshold_strict() -> None:
    # min_roe=0.1 → ROE 0.2 통과·ROE 0.05 배제(경계 초과만·>min 엄격).
    weak = _roe_facts("CIK_E", fy=2022, equity="1000", net_income="50", filed=(2023, 3, 1))  # 0.05
    ident = StubIdentityResolver({"A": "CIK_A", "E": "CIK_E"})
    kept = filter_by_roe(
        {"A", "E"}, identity=ident, financial_facts=[*_PROFIT, *weak],
        as_of=_AS_OF, min_roe=Decimal("0.1"), max_age_days=None,
    )
    assert kept == {"A"}


def test_filter_drops_stale_beyond_max_age() -> None:
    # H5: 폐지직전 신고 멈춘 4년전 흑자만 → max_age 초과 → 배제. max_age None 이면 통과(대조).
    old = _roe_facts("CIK_F", fy=2019, equity="1000", net_income="200", filed=(2020, 3, 1))
    ident = StubIdentityResolver({"F": "CIK_F"})
    stale = filter_by_roe(
        {"F"}, identity=ident, financial_facts=list(old),
        as_of=_AS_OF, min_roe=Decimal(0), max_age_days=548,
    )
    assert stale == set()  # ≈4년 stale 배제
    fresh = filter_by_roe(
        {"F"}, identity=ident, financial_facts=list(old),
        as_of=_AS_OF, min_roe=Decimal(0), max_age_days=None,
    )
    assert fresh == {"F"}  # 상한 없으면 산출(대조군)


def test_filter_excludes_unresolved_ticker() -> None:
    # cik 미해소(빈 문자열) → 배제(조용한 통과 금지).
    ident = StubIdentityResolver({"A": "CIK_A"})  # B 미매핑 → ""
    kept = filter_by_roe(
        {"A", "B"}, identity=ident, financial_facts=list(_PROFIT),
        as_of=_AS_OF, min_roe=Decimal(0), max_age_days=None,
    )
    assert kept == {"A"}


def test_filter_excludes_multimatch_raise() -> None:
    # ticker_history 다중매칭(ValueError) → 배제(게이트 crash 방지)·나머지 정상.
    ident = _MultiMatchResolver({"A": "CIK_A"}, ambiguous={"G"})
    kept = filter_by_roe(
        {"A", "G"}, identity=ident, financial_facts=list(_PROFIT),
        as_of=_AS_OF, min_roe=Decimal(0), max_age_days=None,
    )
    assert kept == {"A"}  # G 모호식별 배제


def test_filter_lookahead_future_filing_excluded() -> None:
    # 룩어헤드 BLOCKING: 흑자 FY2023 이나 공시(filed 2024-08)가 as_of 이후 → 그 시점 미공시 →
    # PIT ROE 없음 → 배제(미래 정보 누설 차단). 다른 FY fact 없으면 흑자여도 통과 못 함.
    future = _roe_facts("CIK_A", fy=2023, equity="1000", net_income="200", filed=(2024, 8, 1))
    ident = StubIdentityResolver({"A": "CIK_A"})
    kept = filter_by_roe(
        {"A"}, identity=ident, financial_facts=future,
        as_of=_AS_OF, min_roe=Decimal(0), max_age_days=None,  # as_of=2024-06-03 < filed
    )
    assert kept == set()  # 미공시 미래 흑자 누설 차단


def test_filter_survivorship_delisted_profitable_kept() -> None:
    # 생존편향 직교성: filter_by_roe 는 폐지 여부를 보지 않음(유니버스 포트 책임). 폐지예정이라도
    # as_of 시점 흑자면 통과 — 폐지종목을 재무만으로 조용히 떨구지 않음(생존편향 유발 금지).
    ident = StubIdentityResolver({"A": "CIK_A"})
    kept = filter_by_roe(
        {"A"}, identity=ident, financial_facts=list(_PROFIT),
        as_of=_AS_OF, min_roe=Decimal(0), max_age_days=None,
    )
    assert kept == {"A"}


# ── engine 배선: off=bit-identical(최우선) / on=ROE→momentum ────────────────


def _cfg(days: list[date], **kw: object) -> BacktestConfig:
    base: dict[str, object] = dict(
        strategy_name="equal_weight_top_n",
        top_n=1,
        lookback_days=5,
        skip_recent_days=0,
        rebalance_freq="monthly",
        cost_bps=Decimal("0"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
        start=days[0],
        end=days[-1],
    )
    base.update(kw)
    return BacktestConfig(**base)  # type: ignore[arg-type]


def _ab_world() -> tuple[FakePriceSeriesPort, FakeUniversePort, list[date]]:
    # A 완만 상승(흑자)·B 급상승(적자). momentum 단독=B 선택, ROE 필터 시 B 배제→A.
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal(100 + i)) for i, d in enumerate(days)]
    b = [PricePoint(d, Decimal(100 + 3 * i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(
        listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={}
    )
    return port, uni, days


def test_engine_off_bit_identical_ignores_facts() -> None:
    # 최우선 회귀: apply_roe_filter=False 면 financial_facts 를 넘겨도 momentum canonical 과 완전
    # 동일(bit-identical). 넘긴 facts 는 B(적자)를 배제하는 내용 — 참조됐다면 결과가 달라짐.
    port, uni, days = _ab_world()
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    cfg_off = _cfg(days)  # apply_roe_filter=False(기본)
    common = dict(
        price_port=port, universe_port=uni, identity=ident,
        strategy=EqualWeightTopN(), liquidity_port=FakeLiquidityPort(None),
    )
    res_none = run(cfg_off, financial_facts=None, **common)  # type: ignore[arg-type]
    res_facts = run(cfg_off, financial_facts=[*_PROFIT, *_LOSS], **common)  # type: ignore[arg-type]
    assert res_none == res_facts  # facts 무시(off) → bit-identical


def test_engine_on_roe_before_momentum_changes_pick() -> None:
    # ROE→momentum: off 는 급상승 B(적자) 선택, on 은 B 배제 후 A(흑자·완만) 선택 → 결과 달라짐.
    port, uni, days = _ab_world()
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    facts = [*_PROFIT, *_LOSS]
    common = dict(
        price_port=port, universe_port=uni, identity=ident,
        strategy=EqualWeightTopN(), liquidity_port=FakeLiquidityPort(None),
        financial_facts=facts,
    )
    res_off = run(_cfg(days), **common)  # type: ignore[arg-type]
    res_on = run(
        _cfg(days, apply_roe_filter=True, min_roe=Decimal(0)), **common  # type: ignore[arg-type]
    )
    # B 급등 배제로 수익 감소·여전히 양(A 흑자 상승)
    assert res_off.total_return > res_on.total_return > Decimal(0)


def test_engine_on_all_excluded_flat_equity() -> None:
    # 전 후보 적자 → 필터 후 공집합 → 보유 0 → equity 불변(총수익 0). 조용한 크래시 없음.
    days = _weekdays(date(2024, 1, 1), 70)
    b = [PricePoint(d, Decimal(100 + 3 * i)) for i, d in enumerate(days)]
    port = FakePriceSeriesPort({"B": b})
    uni = FakeUniversePort(listed={"B": date(2023, 1, 1)}, delisted={})
    res = run(
        _cfg(days, apply_roe_filter=True, min_roe=Decimal(0)),
        price_port=port, universe_port=uni,
        identity=StubIdentityResolver({"B": "CIK_B"}),
        strategy=EqualWeightTopN(), liquidity_port=FakeLiquidityPort(None),
        financial_facts=list(_LOSS),
    )
    assert res.total_return == Decimal(0)  # 보유 없음 → 무변동


# ── benchmark 대칭(H3) ─────────────────────────────────────────────────────


def test_benchmark_off_identical_to_no_filter() -> None:
    # apply_roe_filter=False → identity/facts 넘겨도 미필터 벤치와 bit-identical.
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal("100")) for d in days]  # 평탄
    b = [PricePoint(d, Decimal(100 + 3 * i)) for i, d in enumerate(days)]  # 급상승
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(
        listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={}
    )
    cfg = _cfg(days)
    plain = equal_weight_universe(
        cfg, price_port=port, universe_port=uni, liquidity_port=FakeLiquidityPort(None)
    )
    threaded = equal_weight_universe(
        cfg, price_port=port, universe_port=uni, liquidity_port=FakeLiquidityPort(None),
        identity=StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"}),
        financial_facts=[*_PROFIT, *_LOSS],
    )
    assert plain == threaded


def test_benchmark_on_excludes_loss_member() -> None:
    # H3 대칭: apply_roe_filter=True 시 벤치도 filter_by_roe → 적자 B 제외. A 평탄·B 급상승이라
    # 미필터 벤치(A,B 등가중)는 상승, 필터 벤치(A 만)는 평탄 → on<off(필터가 벤치에 적용됨).
    days = _weekdays(date(2024, 1, 1), 70)
    a = [PricePoint(d, Decimal("100")) for d in days]  # 흑자·평탄
    b = [PricePoint(d, Decimal(100 + 3 * i)) for i, d in enumerate(days)]  # 적자·급상승
    port = FakePriceSeriesPort({"A": a, "B": b})
    uni = FakeUniversePort(
        listed={"A": date(2023, 1, 1), "B": date(2023, 1, 1)}, delisted={}
    )
    ident = StubIdentityResolver({"A": "CIK_A", "B": "CIK_B"})
    facts = [*_PROFIT, *_LOSS]
    off = equal_weight_universe(
        _cfg(days), price_port=port, universe_port=uni,
        liquidity_port=FakeLiquidityPort(None), identity=ident, financial_facts=facts,
    )
    on = equal_weight_universe(
        _cfg(days, apply_roe_filter=True, min_roe=Decimal(0)),
        price_port=port, universe_port=uni, liquidity_port=FakeLiquidityPort(None),
        identity=ident, financial_facts=facts,
    )
    assert off.total_return > on.total_return  # 급상승 B 를 벤치에서 배제 → 벤치 수익 하락
