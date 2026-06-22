"""momentum 부분 푸시다운 결과불변(Task2·ADR-007).

`duckdb_cache.momentum_endpoints`(SQL 끝점 2점·`close*adj_factor` DECIMAL 곱) +
`rules.factors.momentum_from_endpoints`(Python Decimal 나눗셈) 이 **엔진 windowed momentum**
(engine._rank_at = `momentum_universe(load_range(tradable, _window_start(t), t))`) 과 전 필드
bit-identical(score·end/start_date·used_window_points·None)임을 합성 Parquet→build_cache 경유로
봉인한다. 라이브 0(tmp Parquet).

⚠️ 진실원천은 **full-series 가 아니라 windowed momentum** 이다 — 엔진은 윈도우만 로드하고
윈도우 봉 0 종목은 스테일 배제(engine.py:148-152). pushdown 도 윈도우 count(wn) 기준으로 산출해
이 windowed 경로를 재현해야 한다(전체 tot 기준이면 sparse-window 종목에서 발산 — 폐지/정지주).

검증 케이스: 정상·무한소수·adj_factor 변동·graceful(윈도우 전체)·skip·2점 경계·None·룩어헤드·
GOLD(윈도우 밖 전체→양쪽 제외)·GPART(윈도우 일부·graceful-in-window→tot 기준이면 오발산)·빈.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from stockpick.data.duckdb_cache import (
    MomentumEndpoints,
    build_cache,
    connect_readonly,
    momentum_endpoints,
)
from stockpick.data.storage import write_daily_bars
from stockpick.rules._scan import PricePoint
from stockpick.rules.factors import momentum_from_endpoints, momentum_universe
from stockpick.types import DailyBar, Exchange

if TYPE_CHECKING:
    from pathlib import Path

AS_OF = date(2024, 4, 1)  # 월요일
LOOKBACK = 20
SKIP = 3
WINDOW = (LOOKBACK + SKIP) * 2 + 30  # 76 — engine._window_start 와 동일 산식
LO = AS_OF - timedelta(days=WINDOW)  # load_range 하한과 동일 경계


def _weekdays_back(end: date, n: int) -> list[date]:
    """end(포함) 이하 평일 n개를 오름차순으로(마지막 = end 가 평일이면 end)."""
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    out.reverse()
    return out


def _weekdays_fwd(after: date, n: int) -> list[date]:
    """after 초과 평일 n개(미래 — 룩어헤드 무시 검증용)."""
    out: list[date] = []
    d = after + timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _bar(ticker: str, d: date, close: Decimal, adj: Decimal) -> DailyBar:
    return DailyBar(
        ticker=ticker,
        trade_date=d,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        value=None,
        adj_factor=adj,
    )


# (ticker, [(close, adj_factor)] 오름차순, n_future, end_anchor(마지막 봉 날짜))
_SPECS: list[tuple[str, list[tuple[Decimal, Decimal]], int, date]] = [
    # 정상 상승(60봉 ending as_of·윈도우는 최근 ~54봉만 → non-graceful·wn<total 검증)
    ("NORMAL", [(Decimal(100 + i), Decimal("1")) for i in range(60)], 0, AS_OF),
    # 무한소수 비율(소수 close + 소수 adj_factor → end/start 무한소수·Python Decimal 나눗셈)
    (
        "IRRAT",
        [(Decimal(p), Decimal("1.3")) for p in [7, 11, 13, 17, 19, 23, 29, 31, 37, 41] * 4],
        0,
        AS_OF,
    ),
    # adj_factor 봉마다 변동(close*adj_factor 곱 경로 검증)
    (
        "ADJVAR",
        [(Decimal(50 + i), Decimal("1") + Decimal(i % 7) / Decimal(10)) for i in range(30)],
        0,
        AS_OF,
    ),
    # graceful 축소(8봉·전체가 윈도우 안·wn==total·end_idx=8-1-3=4·start clamp 0)
    ("GRACEFUL", [(Decimal(200 + i * 3), Decimal("1")) for i in range(8)], 0, AS_OF),
    # 평탄(score=0)
    ("FLAT", [(Decimal(50), Decimal("1")) for _ in range(30)], 0, AS_OF),
    # 2점 경계(5봉·skip3·end_idx=1·used=2)
    ("TWO", [(Decimal(10 + i * 5), Decimal("1")) for i in range(5)], 0, AS_OF),
    # None(3봉·skip3·end_idx=-1<1 → 산출 불가)
    ("NONE", [(Decimal(100 + i), Decimal("1")) for i in range(3)], 0, AS_OF),
    # 룩어헤드(60봉 ending as_of + 미래 5봉 거대값 — as_of 이하만 사용해야 NORMAL 과 동일)
    ("LOOKAHEAD", [(Decimal(100 + i), Decimal("1")) for i in range(60)], 5, AS_OF),
    # GOLD: 8봉 전체가 윈도우(LO) 이전 → load_range 빈 → momentum_universe·pushdown 양쪽 제외
    ("GOLD", [(Decimal(80 + i * 2), Decimal("1")) for i in range(8)], 0, date(2023, 9, 1)),
    # GPART: 110봉이 윈도우를 가로지름(최근 끝=as_of-약50일·정지/폐지) → 윈도우엔 ~19봉만(graceful-
    #   in-window) 이지만 전체는 non-graceful. tot 기준이면 start 가 발산(이 케이스가 버그 봉인).
    ("GPART", [(Decimal(300 + i), Decimal("1")) for i in range(110)], 0, date(2024, 2, 9)),
]


def _build(tmp_path: Path) -> dict[str, list[PricePoint]]:
    """합성 Parquet 적재 + build_cache. 메모리 비교용 PricePoint 시계열 반환(adjusted=close*adj)."""
    bars: list[DailyBar] = []
    series: dict[str, list[PricePoint]] = {}
    for ticker, closes, n_future, anchor in _SPECS:
        dates = _weekdays_back(anchor, len(closes))
        pts: list[PricePoint] = []
        for d, (close, adj) in zip(dates, closes, strict=True):
            bars.append(_bar(ticker, d, close, adj))
            pts.append(PricePoint(trade_date=d, adjusted=close * adj))
        # 미래봉(룩어헤드) — 거대값. 메모리 series 에도 넣어 ≤as_of 필터까지 검증.
        for d in _weekdays_fwd(anchor, n_future):
            bars.append(_bar(ticker, d, Decimal("99999"), Decimal("1")))
            pts.append(PricePoint(trade_date=d, adjusted=Decimal("99999")))
        series[ticker] = pts
    write_daily_bars(
        bars,
        exchange=Exchange.NASDAQ,
        base_dir=tmp_path,
        source="test",
        ingested_at=datetime(2026, 6, 22, tzinfo=UTC),
    )
    n = build_cache(tmp_path)
    assert n == len(bars)
    return series


def _windowed(series: dict[str, list[PricePoint]]) -> dict[str, list[PricePoint]]:
    """엔진 load_range(tradable, _window_start(t), t) 재현 — [LO, AS_OF] 필터 + 빈 종목 제외."""
    out: dict[str, list[PricePoint]] = {}
    for ticker, pts in series.items():
        win = [p for p in pts if LO <= p.trade_date <= AS_OF]
        if win:  # load_range.setdefault — 행 있는 종목만 dict 생성(봉 0 = 스테일 배제)
            out[ticker] = win
    return out


def _to_points(e: MomentumEndpoints) -> tuple[PricePoint | None, PricePoint | None]:
    end = (
        PricePoint(trade_date=e.end_date, adjusted=e.end_adjusted)
        if e.end_date is not None and e.end_adjusted is not None
        else None
    )
    start = (
        PricePoint(trade_date=e.start_date, adjusted=e.start_adjusted)
        if e.start_date is not None and e.start_adjusted is not None
        else None
    )
    return end, start


def test_momentum_pushdown_bit_identical(tmp_path: Path) -> None:
    series = _build(tmp_path)
    con = connect_readonly(tmp_path)
    try:
        eps = momentum_endpoints(
            con,
            tickers=set(series),
            as_of=AS_OF,
            lookback_days=LOOKBACK,
            skip_recent_days=SKIP,
            window_days=WINDOW,
        )
        # 진실원천 = 엔진과 동일한 windowed momentum(full-series 아님)
        mem = momentum_universe(
            _windowed(series), as_of=AS_OF, lookback_days=LOOKBACK, skip_recent_days=SKIP
        )
        # GOLD 는 윈도우 봉 0 → 양쪽 모두 제외(스테일 배제 동치)
        assert "GOLD" not in eps and "GOLD" not in mem
        assert set(eps) == set(mem), f"ticker 집합 불일치: {set(eps) ^ set(mem)}"
        for ticker, want in mem.items():
            e = eps[ticker]
            end_pt, start_pt = _to_points(e)
            got = momentum_from_endpoints(
                end_point=end_pt,
                start_point=start_pt,
                end_idx=e.end_idx,
                start_idx=e.start_idx,
                lookback_days=LOOKBACK,
            )
            assert got.score == want.score, f"{ticker} score: {got.score} != {want.score}"
            assert got.end_date == want.end_date, f"{ticker} end_date"
            assert got.start_date == want.start_date, f"{ticker} start_date"
            assert got.used_window_points == want.used_window_points, f"{ticker} used"
            assert got.requested_lookback_days == want.requested_lookback_days, f"{ticker} req"
    finally:
        con.close()


def test_momentum_endpoints_lookahead(tmp_path: Path) -> None:
    """LOOKAHEAD == NORMAL: as_of 이후 거대 미래봉이 끝점에 누설되지 않음(룩어헤드 봉인)."""
    series = _build(tmp_path)
    con = connect_readonly(tmp_path)
    try:
        eps = momentum_endpoints(
            con,
            tickers=set(series),
            as_of=AS_OF,
            lookback_days=LOOKBACK,
            skip_recent_days=SKIP,
            window_days=WINDOW,
        )
        assert eps["LOOKAHEAD"] == eps["NORMAL"]
    finally:
        con.close()


def test_momentum_endpoints_empty(tmp_path: Path) -> None:
    _build(tmp_path)
    con = connect_readonly(tmp_path)
    try:
        assert (
            momentum_endpoints(
                con,
                tickers=set(),
                as_of=AS_OF,
                lookback_days=LOOKBACK,
                skip_recent_days=SKIP,
                window_days=WINDOW,
            )
            == {}
        )
    finally:
        con.close()
