"""profile CLI(관측성 Task2) — 라이브 collector·Pushgateway push·DuckDB 메모리·main 스모크.

라이브 0(합성 Parquet→build_cache·서버/네트워크 모킹). Pushgateway/start_http_server 미접속.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from prometheus_client.core import REGISTRY

from stockpick.backtest import profile
from stockpick.backtest.adapters import DuckDBPriceSeriesPort, ParquetPriceSeriesPort
from stockpick.backtest.profile import _duckdb_memory, _LivePhaseCollector, _push_summary
from stockpick.backtest.profile_types import PhaseTimer
from stockpick.data.duckdb_cache import build_cache
from stockpick.data.storage import write_daily_bars
from stockpick.types import DailyBar, Exchange

if TYPE_CHECKING:
    from pathlib import Path


def _weekdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _build_cache(tmp_path: Path, *, n_days: int = 40) -> None:
    days = _weekdays(date(2024, 1, 1), n_days)
    bars = [
        DailyBar(
            ticker=tk,
            trade_date=d,
            open=Decimal(base + i),
            high=Decimal(base + i),
            low=Decimal(base + i),
            close=Decimal(base + i),
            volume=1000,
            value=None,
            adj_factor=Decimal("1"),
        )
        for tk, base in (("AAA", 100), ("BBB", 50), ("CCC", 200))
        for i, d in enumerate(days)
    ]
    write_daily_bars(
        bars,
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="test",
        ingested_at=datetime(2026, 6, 23, tzinfo=UTC),
    )
    build_cache(tmp_path)


def test_live_collector_yields_phase_and_progress() -> None:
    timer = PhaseTimer()
    timer.observe("rank", 1.5)
    timer.observe("hold_load", 0.5)
    timer.tick_rebalance()
    timer.tick_rebalance()
    families = {m.name: m for m in _LivePhaseCollector(timer).collect()}
    assert "stockpick_backtest_phase_seconds_live" in families
    assert "stockpick_backtest_progress_rebalance" in families
    live = families["stockpick_backtest_phase_seconds_live"]
    phase_samples = {s.labels["phase"]: s.value for s in live.samples}
    assert phase_samples["rank"] == 1.5
    progress = families["stockpick_backtest_progress_rebalance"].samples[0].value
    assert progress == 2.0


def test_live_collector_in_generate_latest() -> None:
    """collector 등록 후 /metrics 텍스트(generate_latest)에 phase·진행·RSS 메트릭 노출."""
    from prometheus_client import generate_latest

    timer = PhaseTimer()
    timer.observe("rank", 0.3)
    collector = _LivePhaseCollector(timer)
    REGISTRY.register(collector)
    try:
        text = generate_latest(REGISTRY).decode()
        assert "stockpick_backtest_phase_seconds_live" in text
        assert "stockpick_backtest_progress_rebalance" in text
        assert "process_resident_memory_bytes" in text  # ProcessCollector 자동(RSS 곡선)
    finally:
        REGISTRY.unregister(collector)


def test_push_summary_skip_when_no_gateway() -> None:
    # PUSHGATEWAY_URL 없으면 push 안 함(예외 없이 skip).
    pp = PhaseTimer().snapshot(python_peak_bytes=1, rss_peak_bytes=2)
    _push_summary(
        None, "test", total_seconds=1.0, phase=pp, n_rebalances=3, n_delisted=0, duckdb_used=None
    )


def test_push_summary_pushes_with_round(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def _fake_push(
        gateway: str, *, job: str, grouping_key: dict[str, str], registry: object
    ) -> None:
        calls.append({"gateway": gateway, "job": job, "round": grouping_key.get("round")})

    monkeypatch.setattr(profile, "push_to_gateway", _fake_push)
    pp = PhaseTimer().snapshot(python_peak_bytes=10, rss_peak_bytes=20)
    _push_summary(
        "pushgateway:9091",
        "before",
        total_seconds=5.0,
        phase=pp,
        n_rebalances=7,
        n_delisted=1,
        duckdb_used=30,
    )
    assert calls == [{"gateway": "pushgateway:9091", "job": "backtest_profile", "round": "before"}]


def test_duckdb_memory_duck_vs_parquet(tmp_path: Path) -> None:
    _build_cache(tmp_path)
    dport = DuckDBPriceSeriesPort(tmp_path)
    try:
        used, limit = _duckdb_memory(dport)
        assert used is not None and used >= 0  # 현재 사용량(post-run·best-effort)
        assert limit is not None  # memory_limit 설정 문자열
    finally:
        dport.close()
    # 비-DuckDB 포트 → (None, None)
    assert _duckdb_memory(ParquetPriceSeriesPort(tmp_path)) == (None, None)


def test_main_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """main 전체 경로 — 합성 캐시·서버/레지스터/푸시 모킹(글로벌 상태·네트워크 회피)."""
    _build_cache(tmp_path)
    monkeypatch.setattr(profile, "start_http_server", lambda _port: None)
    monkeypatch.setattr(REGISTRY, "register", lambda _c: None)  # 글로벌 싱글톤(profile 도 동일)
    monkeypatch.setenv("STOCKPICK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("PUSHGATEWAY_URL", raising=False)  # push skip
    assert profile.main() == 0
