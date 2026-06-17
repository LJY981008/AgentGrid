"""거래일 집합 → 리밸런싱 날짜·보유구간. 합성 금지 — 데이터의 실제 거래일만 입력.

`holding_periods` 는 engine·benchmark 가 공유하는 **회계 경계 단일 출처** — 진입=리밸일 t 다음
거래일(룩어헤드 t+1)·청산=다음 리밸 진입일. 두 모듈이 같은 구간 계산을 쓰게 해 드리프트(한쪽만
회계 규칙 수정 시 자산곡선 어긋남)를 방지한다.
"""

from __future__ import annotations

import bisect
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from datetime import date

_QUARTER_MONTHS = frozenset({1, 4, 7, 10})


class RebalancePlan(NamedTuple):
    """리밸런싱 계획 — 초기자본 앵커 날짜(리밸 없으면 None) + (리밸일, 진입일, 청산일) 구간 목록."""

    anchor: date | None
    periods: list[tuple[date, date, date]]


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


def _next_day(days: list[date], after: date) -> date | None:
    """days 에서 after **초과** 첫 거래일(진입 t+1·청산 t'+1 규칙). 없으면 None."""
    idx = bisect.bisect_right(days, after)
    return days[idx] if idx < len(days) else None


def holding_periods(
    all_days: list[date],
    *,
    start: date,
    end: date,
    freq: str,
) -> RebalancePlan:
    """거래일·기간·주기 → 리밸런싱 계획((리밸일 t, 진입일, 청산일) 목록 + 앵커).

    진입 = t **다음** 거래일(룩어헤드 t+1·동시성 누설 차단). 청산 = 다음 리밸의 진입일(= 다음
    리밸일의 다음 거래일), 마지막 구간은 in_range 끝일. 유효 구간(entry<=exit)만 포함(데이터 끝에
    걸린 리밸은 제외). 앵커 = 리밸이 있으면 in_range 첫날(초기자본 1.0 기준점), 없으면 None.

    engine·benchmark 가 이 함수 하나를 공유한다 — 회계 경계(진입/청산/스킵)의 단일 출처.
    """
    in_range = [d for d in all_days if start <= d <= end]
    reb = rebalance_dates(in_range, freq=freq)
    anchor = in_range[0] if reb else None
    last_day = in_range[-1] if in_range else None
    periods: list[tuple[date, date, date]] = []
    if last_day is not None:
        for i, t in enumerate(reb):
            entry_day = _next_day(all_days, t)
            if entry_day is None:
                break
            next_reb = reb[i + 1] if i + 1 < len(reb) else None
            exit_day = _next_day(all_days, next_reb) if next_reb is not None else last_day
            if exit_day is None:
                exit_day = last_day
            if entry_day > exit_day:
                continue  # 진입일이 청산일 초과(데이터 끝) — 보유 구간 없음, 제외
            periods.append((t, entry_day, exit_day))
    return RebalancePlan(anchor=anchor, periods=periods)
