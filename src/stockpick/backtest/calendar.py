"""거래일 집합 → 리밸런싱 날짜(각 기간 첫 거래일). 합성 금지 — 데이터의 실제 거래일만 입력."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

_QUARTER_MONTHS = frozenset({1, 4, 7, 10})


def rebalance_dates(trading_days: list[date], *, freq: str) -> list[date]:
    """정렬된 거래일에서 각 (연·월) [분기면 분기시작월] 첫 거래일을 리밸일로. 빈 입력=빈 리스트."""
    if freq not in ("monthly", "quarterly"):
        msg = f"rebalance_freq 는 monthly|quarterly (받음={freq})"
        raise ValueError(msg)
    ordered = sorted(trading_days)
    out: list[date] = []
    seen: set[tuple[int, int]] = set()
    for d in ordered:
        if freq == "quarterly" and d.month not in _QUARTER_MONTHS:
            continue
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out
