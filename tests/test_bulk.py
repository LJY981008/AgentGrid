"""data/bulk.py 체크포인트·재시도 — 라이브 0(httpx.MockTransport)·PG 불요(Task3 부분).

검증: 체크포인트 JSONL 라운드트립·done/empty skip·failed 재시도·마지막상태 우선 / fetch_with_retry
429 재시도·transient 5xx 재시도·4xx raise·auth 전파·429 소진 raise.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from stockpick.data.bulk import Checkpoint, fetch_with_retry
from stockpick.data.eodhd import (
    EodhdAuthError,
    EodhdRateLimitError,
    EodhdResponseError,
    EodhdSource,
)

_EOD_ROW: dict[str, object] = {
    "date": "2024-01-02",
    "open": 1.0,
    "high": 1.0,
    "low": 1.0,
    "close": 1.0,
    "adjusted_close": 1.0,
    "volume": 1,
}


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EODHD_API_KEY", "test-token")


def _source(handler: httpx.MockTransport) -> EodhdSource:
    return EodhdSource(client=httpx.Client(transport=handler))


def _noop_sleep(_seconds: float) -> None:
    return None


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "cp.jsonl"
    cp = Checkpoint.load(p)
    cp.mark("AAA", "done")
    cp.mark("BBB", "empty")
    cp.mark("CCC", "failed")
    reloaded = Checkpoint.load(p)
    assert reloaded.should_skip("AAA")  # done → skip
    assert reloaded.should_skip("BBB")  # empty → skip
    assert not reloaded.should_skip("CCC")  # failed → 재시도
    assert not reloaded.should_skip("DDD")  # 미기록 → 처리
    assert reloaded.counts() == {"done": 1, "empty": 1, "failed": 1}


def test_checkpoint_last_status_wins(tmp_path: Path) -> None:
    p = tmp_path / "cp.jsonl"
    cp = Checkpoint.load(p)
    cp.mark("AAA", "failed")
    cp.mark("AAA", "done")  # 재처리 후 성공
    assert Checkpoint.load(p).should_skip("AAA")  # 마지막 done 우선


def test_fetch_with_retry_429_then_success() -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={}, headers={"Retry-After": "1"})
        return httpx.Response(200, json=[_EOD_ROW])

    bars = fetch_with_retry(_source(httpx.MockTransport(handler)), "AAA", sleep_fn=_noop_sleep)
    assert len(bars) == 1
    assert calls["n"] == 2  # 429 후 재시도 성공


def test_fetch_with_retry_transient_5xx_retried() -> None:
    calls = {"n": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=[_EOD_ROW])

    bars = fetch_with_retry(_source(httpx.MockTransport(handler)), "AAA", sleep_fn=_noop_sleep)
    assert len(bars) == 1
    assert calls["n"] == 2  # transient 5xx 재시도 성공


def test_fetch_with_retry_4xx_raises() -> None:
    # per-ticker 4xx(<500) → raise(호출부 failed 기록·계속).
    handler = httpx.MockTransport(lambda _r: httpx.Response(404, json={}))
    with pytest.raises(EodhdResponseError):
        fetch_with_retry(_source(handler), "AAA", sleep_fn=_noop_sleep)


def test_fetch_with_retry_auth_propagates() -> None:
    # auth(401) → 전파(전체 중단).
    handler = httpx.MockTransport(lambda _r: httpx.Response(401, json={}))
    with pytest.raises(EodhdAuthError):
        fetch_with_retry(_source(handler), "AAA", sleep_fn=_noop_sleep)


def test_fetch_with_retry_429_exhausts_raises() -> None:
    # 429 max_retries 초과 → raise(호출부 일일쿼터 graceful stop 판단).
    handler = httpx.MockTransport(lambda _r: httpx.Response(429, json={}))
    with pytest.raises(EodhdRateLimitError):
        fetch_with_retry(_source(handler), "AAA", max_retries=2, sleep_fn=_noop_sleep)
