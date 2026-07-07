"""M4 P7 — 추적 API 흐름 테스트(InMemory repo DI·합성 Parquet·라이브 0).

상태 규약 봉인: open 유일 409·Top5 확정 전 BUY 422·top5⊆Top20 422·미등록 종목 422·
SELL 초과 422·SPY 부재 성과 422·close 정상 흐름·closed 후 변경 409.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from stockpick.api.app import create_app
from stockpick.api.deps import get_base_dir, get_round_repo
from stockpick.data.benchmark import BENCHMARK_SUBDIR
from stockpick.data.storage import write_daily_bars
from stockpick.tracking.fakes import InMemoryRoundRepository
from stockpick.types import DailyBar, Exchange

if TYPE_CHECKING:
    from collections.abc import Iterator

_TICKERS = ("AAA", "BBB", "CCC")


def _weekdays_until_today(n: int) -> list[date]:
    out: list[date] = []
    d = date.today()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _bar(ticker: str, d: date, close: Decimal) -> DailyBar:
    return DailyBar(
        ticker=ticker, trade_date=d, open=close, high=close, low=close, close=close,
        volume=10_000, value=None, adj_factor=Decimal(1),
    )


@pytest.fixture
def repo() -> InMemoryRoundRepository:
    return InMemoryRoundRepository(stock_ids={t: i + 1 for i, t in enumerate(_TICKERS)})


@pytest.fixture
def client(tmp_path: Path, repo: InMemoryRoundRepository) -> Iterator[TestClient]:
    base_dir = tmp_path / "parquet"
    days = _weekdays_until_today(170)  # momentum lookback 126+skip 21 워밍업 충분
    bars: list[DailyBar] = []
    for i, d in enumerate(days):
        bars.append(_bar("AAA", d, Decimal(100 + i)))  # 상승 모멘텀
        bars.append(_bar("BBB", d, Decimal("100")))  # 평탄
        bars.append(_bar("CCC", d, Decimal(200 - i // 2)))  # 하락
    write_daily_bars(bars, exchange=Exchange.NASDAQ, base_dir=base_dir, source="test")

    app = create_app()
    app.dependency_overrides[get_base_dir] = lambda: base_dir
    app.dependency_overrides[get_round_repo] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _write_spy(client: TestClient) -> None:
    base_dir: Path = client.app.dependency_overrides[get_base_dir]()  # type: ignore[attr-defined]
    days = _weekdays_until_today(170)
    spy = [_bar("SPY", d, Decimal(500 + i)) for i, d in enumerate(days)]
    write_daily_bars(
        spy, exchange=Exchange.NYSE_ARCA, base_dir=base_dir / BENCHMARK_SUBDIR, source="test"
    )


def _create_round(client: TestClient) -> dict[str, object]:
    r = client.post("/api/rounds", json={"label": "2026-07"})
    assert r.status_code == 200, r.text
    payload: dict[str, object] = r.json()
    return payload


def test_round_lifecycle_full_flow(client: TestClient) -> None:
    # 생성 — Top20 스냅샷(합성 3종목 전부)·validated false·warning 상시(§4.1).
    rnd = _create_round(client)
    assert rnd["validated"] is False
    assert rnd["warning"]
    top20 = rnd["top20"]
    assert isinstance(top20, list)
    tickers = {e["ticker"] for e in top20}
    assert tickers <= set(_TICKERS)
    assert all(e["anchor_close"] is not None for e in top20)  # 앵커가 동결
    rid = rnd["id"]

    # open 유일 — 두 번째 생성 409.
    assert client.post("/api/rounds", json={"label": "2026-08"}).status_code == 409

    # Top5 확정 전 BUY 금지(규율 순서).
    trade_body = {
        "ticker": "AAA", "side": "BUY", "quantity": "10", "price": "100",
        "executed_on": date.today().isoformat(),
    }
    assert client.post(f"/api/rounds/{rid}/trades", json=trade_body).status_code == 422

    # top5 ⊆ Top20 검증.
    bad = client.patch(f"/api/rounds/{rid}", json={"memo": "토의 요약본", "top5": ["ZZZ"]})
    assert bad.status_code == 422
    ok = client.patch(f"/api/rounds/{rid}", json={"memo": "토의 요약본", "top5": ["AAA"]})
    assert ok.status_code == 200

    # 입금 없이 BUY → 현금 음수 422. 입금 후 BUY 200.
    assert client.post(f"/api/rounds/{rid}/trades", json=trade_body).status_code == 422
    flow = client.post(
        f"/api/rounds/{rid}/cash-flows",
        json={"amount": "2000", "flowed_on": date.today().isoformat()},
    )
    assert flow.status_code == 200
    assert client.post(f"/api/rounds/{rid}/trades", json=trade_body).status_code == 200

    # 미등록 종목 422 · SELL 초과 422.
    unknown = dict(trade_body, ticker="ZZZ")
    assert client.post(f"/api/rounds/{rid}/trades", json=unknown).status_code == 422
    oversell = dict(trade_body, side="SELL", quantity="11")
    assert client.post(f"/api/rounds/{rid}/trades", json=oversell).status_code == 422

    # SPY 부재 → 성과 422(측정불가 명시·조용한 0 금지). 적재 후 200.
    assert client.get(f"/api/rounds/{rid}/performance").status_code == 422
    _write_spy(client)
    perf = client.get(f"/api/rounds/{rid}/performance")
    assert perf.status_code == 200, perf.text
    body = perf.json()
    assert body["return_convention"] == "price"  # 배당 미반영 명시(척도 계약)
    assert body["validated"] is False
    assert body["verdict_deferred"] is True  # 누적 pick 1 < 20 — 판정 유보 고정
    assert body["stale"] is False
    assert body["actual"]["index"]  # 4계열 산출
    assert body["spy"]["cumulative_return"] is not None

    # 마감(구조화 회고 필수) → closed·성과 동결 → 이후 변경 409.
    retro = {
        "judgment_good": "분산 유지 판단 근거",
        "judgment_bad": "추격 매수 근거 부족",
        "rule_change": "없음",
    }
    closed = client.post(f"/api/rounds/{rid}/close", json=retro)
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert client.post(f"/api/rounds/{rid}/trades", json=trade_body).status_code == 409
    trade_id = next(t["id"] for t in closed.json()["trades"])
    void = client.post(f"/api/trades/{trade_id}/void", json={"reason": "테스트 사유"})
    assert void.status_code == 409  # closed 라운드 거래 void 금지(동결 발산 차단)

    # close 후 새 라운드 가능 + 이월 carry-in 파생(AAA 10주).
    rnd2 = client.post("/api/rounds", json={"label": "2026-08"})
    assert rnd2.status_code == 200
    carry = rnd2.json()["carry_in"]
    assert carry and carry[0]["ticker"] == "AAA"
    assert carry[0]["quantity"] == 10.0


def test_round_missing_404(client: TestClient) -> None:
    assert client.get("/api/rounds/999").status_code == 404
    assert client.get("/api/rounds/999/performance").status_code == 404


def test_retrospective_min_length_enforced(client: TestClient) -> None:
    rnd = _create_round(client)
    rid = rnd["id"]
    _write_spy(client)
    weak = {"judgment_good": ".", "judgment_bad": ".", "rule_change": "."}  # '.' 무력화 차단
    assert client.post(f"/api/rounds/{rid}/close", json=weak).status_code == 422
