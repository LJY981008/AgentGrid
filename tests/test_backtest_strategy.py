from datetime import date
from decimal import Decimal

from stockpick.backtest.strategy import EqualWeightTopN, ScoreWeightTopN
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
