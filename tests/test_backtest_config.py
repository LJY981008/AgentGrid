from datetime import date
from decimal import Decimal

import pytest

from stockpick.backtest.config import BacktestConfig


def _cfg(**kw: object) -> BacktestConfig:
    base = dict(
        strategy_name="equal_weight_top_n",
        top_n=5,
        lookback_days=126,
        skip_recent_days=21,
        rebalance_freq="monthly",
        cost_bps=Decimal("10"),
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
        start=date(2024, 1, 1),
        end=date(2024, 12, 31),
    )
    base.update(kw)
    return BacktestConfig(**base)  # type: ignore[arg-type]


def test_fingerprint_deterministic_same_meaning() -> None:
    a = _cfg(cost_bps=Decimal("10")).fingerprint()
    b = _cfg(cost_bps=Decimal("10.0")).fingerprint()
    assert a == b


def test_fingerprint_changes_on_param_change() -> None:
    assert _cfg(top_n=5).fingerprint() != _cfg(top_n=10).fingerprint()


def test_fingerprint_is_hex_sha256() -> None:
    fp = _cfg().fingerprint()
    assert len(fp) == 64 and all(c in "0123456789abcdef" for c in fp)


# ── decile portfolio 필드(ADR-010 #3 — 동결 우회 차단·fingerprint 포함) ──


def test_fingerprint_changes_on_portfolio_pct() -> None:
    # portfolio_pct(decile 비율) = 룰 정체성 → fingerprint 갈라져야(동결 우회 차단).
    assert _cfg().fingerprint() != _cfg(portfolio_pct=Decimal("0.1")).fingerprint()
    assert (
        _cfg(portfolio_pct=Decimal("0.1")).fingerprint()
        != _cfg(portfolio_pct=Decimal("0.2")).fingerprint()
    )


def test_fingerprint_changes_on_decile_min_holdings() -> None:
    assert _cfg(decile_min_holdings=20).fingerprint() != _cfg(decile_min_holdings=30).fingerprint()


def test_portfolio_pct_none_is_default() -> None:
    # 기본값 None = 고정 top_n 모드(기존 동작 불변). decile 은 명시 opt-in.
    assert _cfg().portfolio_pct is None


def test_portfolio_pct_out_of_range_raises() -> None:
    # 0<pct<=1 비율(외부 의미). 0·음수·>1 은 조용한 오설정 금지(loud fail).
    with pytest.raises(ValueError, match="portfolio_pct"):
        _cfg(portfolio_pct=Decimal("0"))
    with pytest.raises(ValueError, match="portfolio_pct"):
        _cfg(portfolio_pct=Decimal("1.5"))


def test_decile_min_holdings_non_positive_raises() -> None:
    with pytest.raises(ValueError, match="decile_min_holdings"):
        _cfg(decile_min_holdings=0)
