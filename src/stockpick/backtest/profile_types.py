"""백테스트 phase 계측 계약 — **stdlib 만**(prometheus 무관·모듈경계 BLOCKING).

엔진(backtest)이 prometheus 를 import 하지 않고 phase 별 wall 시간을 측정하기 위한 순수 dataclass +
누적기 + 컨텍스트매니저. Prometheus 변환은 상위층(profile CLI·api)이 `BacktestResult.phase_profile`
를 소비해 수행한다. `profile=None`(기본) 이면 계측 0 — 엔진 결과·성능 불변(결과불변 BLOCKING).
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class PhaseProfile:
    """phase 별 누적 wall(초)·호출수 + peak 메모리 3종(profile CLI 가 채움·없으면 None).

    durations/counts = 엔진이 측정한 phase 분해(rank/hold_load/hold_return/members/bench_hold).
    *_peak_bytes = peak 메모리 범인 가림용 — python(tracemalloc)·rss(ru_maxrss)·duckdb(DuckDB 보고).
    """

    durations: dict[str, float]
    counts: dict[str, int]
    python_peak_bytes: int | None = None
    rss_peak_bytes: int | None = None
    duckdb_peak_bytes: int | None = None


class PhaseTimer:
    """리밸 루프 phase 누적기(엔진 주입·선택). 라이브 곡선용 진행 리밸 idx 노출.

    엔진은 `observe`/`tick_rebalance` 만 호출(stdlib). prometheus collector(상위)는 `durations`·
    `current_rebalance` 를 읽어 라이브 노출. 미주입(None) 시 엔진은 계측 분기를 타지 않는다.
    """

    def __init__(self) -> None:
        self._dur: dict[str, float] = defaultdict(float)
        self._cnt: dict[str, int] = defaultdict(int)
        self.current_rebalance: int = 0  # 라이브 진행 곡선(profile /metrics collector 가 읽음)

    def observe(self, name: str, seconds: float) -> None:
        self._dur[name] += seconds
        self._cnt[name] += 1

    def tick_rebalance(self) -> None:
        self.current_rebalance += 1

    @property
    def durations(self) -> dict[str, float]:
        # 격리 복사 반환(의도) — 라이브 collector가 루프 중 읽어도 부분갱신 dict(torn read) 미관측.
        return dict(self._dur)

    def snapshot(
        self,
        *,
        python_peak_bytes: int | None = None,
        rss_peak_bytes: int | None = None,
        duckdb_peak_bytes: int | None = None,
    ) -> PhaseProfile:
        return PhaseProfile(
            dict(self._dur),
            dict(self._cnt),
            python_peak_bytes,
            rss_peak_bytes,
            duckdb_peak_bytes,
        )


@contextmanager
def timed(profile: PhaseTimer | None, name: str) -> Iterator[None]:
    """phase 시간 측정 컨텍스트 — `profile=None` 이면 즉시 yield(계측 0·결과·성능 불변)."""
    if profile is None:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        profile.observe(name, time.perf_counter() - t0)
