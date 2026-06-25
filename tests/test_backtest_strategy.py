from datetime import date
from decimal import Decimal

from stockpick.backtest.strategy import (
    EqualWeightTopN,
    ScoreWeightTopN,
    TopDecileEqualWeight,
)
from stockpick.types import Exchange, TopEntry


def _entry(cik: str, rank: int, score: float) -> TopEntry:
    return TopEntry(
        cik=cik,
        ticker=cik,
        exchange=Exchange.NASDAQ,
        rank=rank,
        score=score,
        rule_version="v0",
        factors={"momentum": score},
    )


def test_equal_weight_sums_to_one_and_uniform() -> None:
    ranked = [_entry("A", 1, 0.5), _entry("B", 2, 0.3), _entry("C", 3, 0.1)]
    w = EqualWeightTopN().weights(ranked, as_of=date(2024, 6, 1))
    assert w == {"A": Decimal("1") / 3, "B": Decimal("1") / 3, "C": Decimal("1") / 3}
    # 균등성 + 합≈1 (Decimal 1/3 나눗셈은 28자리 dust 라 정확히 1이 안 됨 — 무시 가능 오차)
    assert abs(sum(w.values(), Decimal(0)) - Decimal("1")) < Decimal("1e-20")


def test_score_weight_proportional_positive_only() -> None:
    ranked = [_entry("A", 1, 0.6), _entry("B", 2, 0.2)]
    w = ScoreWeightTopN().weights(ranked, as_of=date(2024, 6, 1))
    assert w["A"] == Decimal("0.6") / Decimal("0.8")
    assert w["B"] == Decimal("0.2") / Decimal("0.8")


def test_score_weight_nonpositive_total_falls_back_equal() -> None:
    ranked = [_entry("A", 1, -0.1), _entry("B", 2, -0.2)]
    w = ScoreWeightTopN().weights(ranked, as_of=date(2024, 6, 1))
    assert w == {"A": Decimal("1") / 2, "B": Decimal("1") / 2}


def test_empty_ranked_empty_weights() -> None:
    assert EqualWeightTopN().weights([], as_of=date(2024, 6, 1)) == {}
    assert ScoreWeightTopN().weights([], as_of=date(2024, 6, 1)) == {}


# ── TopDecileEqualWeight (ADR-010 #3 — top decile·종목수 가변·floor 가드) ──


def _ranked(n: int) -> list[TopEntry]:
    # rank 1..n, score 내림차순(이미 정렬된 후보 풀 — 전략은 상위 decile 선택만).
    return [_entry(f"T{i:04d}", i + 1, float(n - i)) for i in range(n)]


def test_top_decile_selects_ten_percent_equal_weight() -> None:
    # N=300, pct=0.1 → 30종목(floor 20 보다 큼)·등가중 1/30. 선택은 상위 rank 30개.
    s = TopDecileEqualWeight(pct=Decimal("0.1"), min_holdings=20)
    w = s.weights(_ranked(300), as_of=date(2024, 6, 1))
    assert len(w) == 30
    assert set(w) == {f"T{i:04d}" for i in range(30)}  # 상위 30(rank 1..30)
    assert all(v == Decimal(1) / Decimal(30) for v in w.values())
    assert abs(sum(w.values(), Decimal(0)) - Decimal(1)) < Decimal("1e-20")


def test_top_decile_floor_applies_for_small_universe() -> None:
    # N=100, 10%=10 < floor 20 → floor 가 binding → 20종목(초기·소형 유니버스 과집중 방지).
    s = TopDecileEqualWeight(pct=Decimal("0.1"), min_holdings=20)
    w = s.weights(_ranked(100), as_of=date(2024, 6, 1))
    assert len(w) == 20


def test_top_decile_ceil_rounds_up_fraction() -> None:
    # N=255, 10%=25.5 → ceil 26(부분 종목 없음·올림). floor 20 비binding.
    s = TopDecileEqualWeight(pct=Decimal("0.1"), min_holdings=20)
    w = s.weights(_ranked(255), as_of=date(2024, 6, 1))
    assert len(w) == 26


def test_top_decile_caps_at_universe_size() -> None:
    # N=10 < floor 20 → min(floor, N)=10(전 종목 보유·floor 초과 불가).
    s = TopDecileEqualWeight(pct=Decimal("0.1"), min_holdings=20)
    w = s.weights(_ranked(10), as_of=date(2024, 6, 1))
    assert len(w) == 10
    assert all(v == Decimal(1) / Decimal(10) for v in w.values())


def test_top_decile_empty_ranked_empty_weights() -> None:
    s = TopDecileEqualWeight(pct=Decimal("0.1"), min_holdings=20)
    assert s.weights([], as_of=date(2024, 6, 1)) == {}


def test_top_decile_name_is_distinct_rule_identity() -> None:
    # strategy_name = 룰 정체성(compute_rule_signature) — equal_weight 과 구분돼야.
    s = TopDecileEqualWeight(pct=Decimal("0.1"), min_holdings=20)
    assert s.name == "top_decile_equal_weight"
    assert s.name != EqualWeightTopN().name
