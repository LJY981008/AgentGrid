"""거래비용 순수함수 — 회전율(turnover) × bps → 비용 분율(Decimal). 마찰만(폐지청산은 engine)."""

from __future__ import annotations

from decimal import Decimal

_BPS = Decimal("10000")


def apply_cost_fraction(turnover: Decimal, cost_bps: Decimal) -> Decimal:
    """turnover(편출+편입 절대비중 합, 단방향 0~2)·cost_bps → 비용 분율. equity *= (1-분율)."""
    if turnover < 0 or cost_bps < 0:
        msg = f"turnover·cost_bps 음수 불가(turnover={turnover}, bps={cost_bps})"
        raise ValueError(msg)
    return (turnover * cost_bps / _BPS).quantize(Decimal("0.0001"))
