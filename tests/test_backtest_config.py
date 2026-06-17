from datetime import date
from decimal import Decimal

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
