"""프로덕션 포트 구현체 — Parquet/DuckDB(_scan 위임). 데모·실전이 주입한다.

⚠️ UniversePort(`PriceDerivedUniverse`): 무료 골격엔 종목마스터(listed/delisted)가 저장소에 없다
(EODHD 미제공). 가격 존재로 유니버스를 도출하면 survivorship 한계(미래상장 포함 불가·실폐지 미반영)
가 있으나, 골격 단계의 정직한 차선이다(data_caveats 에 한계 명시). 결제 후 종목마스터(TASK-E/S5)·
ticker_history 적재 시 listed/delisted 기반 정식 UniversePort 로 교체한다. 합성 폐지 주입이 필요한
테스트는 `fakes.FakeUniversePort` 를 쓴다(프로덕션 경로와 분리).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from ..data import duckdb_cache
from ..rules import _scan, factors
from .ports import momentum_window_days

if TYPE_CHECKING:
    from pathlib import Path

    from ..rules._scan import PricePoint
    from ..rules.factors import MomentumScore
    from ..types import Exchange
    from .ports import PriceSeriesPort, UniversePort

logger = logging.getLogger(__name__)

_SNAPSHOT_NAME = "stock_snapshot.json"

# cache.duckdb daily_bar 컬럼 = ticker,trade_date,close,adj_factor(exchange 없음·hive 파티션).
# _scan 과 동일 정렬(ORDER BY ticker,trade_date)·adjusted=close*adj_factor Python 곱(Parquet 동치).
_SQL_LOAD_RANGE = (
    "SELECT ticker, trade_date, close, adj_factor FROM daily_bar "
    "WHERE ticker = ANY($t) AND trade_date BETWEEN $s AND $e ORDER BY ticker, trade_date"
)
_SQL_LOAD_AS_OF = (
    "SELECT ticker, trade_date, close, adj_factor FROM daily_bar "
    "WHERE trade_date <= $a ORDER BY ticker, trade_date"
)
_SQL_LOAD_ALL = (
    "SELECT ticker, trade_date, close, adj_factor FROM daily_bar ORDER BY ticker, trade_date"
)
_SQL_TRADING_DAYS = "SELECT DISTINCT trade_date FROM daily_bar ORDER BY trade_date"
# 멤버십만(load_range 동일 WHERE·봉≥1 종목)·DISTINCT ticker — PricePoint 미물질화.
# close/adj_factor NOT NULL 명시(self-contained·load_range NULL→TypeError 와 동치·_scan 동일).
_SQL_TICKERS_WITH_DATA = (
    "SELECT DISTINCT ticker FROM daily_bar WHERE ticker = ANY($t) "
    "AND trade_date BETWEEN $s AND $e AND close IS NOT NULL AND adj_factor IS NOT NULL"
)


def _series_from_price_rows(rows: list[tuple[object, ...]]) -> dict[str, list[PricePoint]]:
    """cache 행(ticker,trade_date,close,adj_factor) → {ticker:[PricePoint]} (타입 narrowing).

    adjusted = close * adj_factor 를 **Python Decimal** 로 합성(_scan 과 동일 — Parquet 포트와
    bit-identical). 예상 밖 타입이면 추측 변환 없이 실패(실패 명확 보고).
    """
    series: dict[str, list[PricePoint]] = {}
    for row in rows:
        ticker, trade_date, close, adj_factor = row
        if not (
            isinstance(ticker, str)
            and isinstance(trade_date, date)
            and isinstance(close, Decimal)
            and isinstance(adj_factor, Decimal)
        ):
            msg = f"예상치 못한 가격 행 타입: {[type(x).__name__ for x in row]}"
            raise TypeError(msg)
        series.setdefault(ticker, []).append(
            _scan.PricePoint(trade_date=trade_date, adjusted=close * adj_factor)
        )
    return series


class ParquetPriceSeriesPort:
    """daily_bar Parquet → 수정주가 시계열(_scan 위임). full_series 는 as_of=None 전구간."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._full: dict[str, list[PricePoint]] | None = None

    def load(self, *, as_of: date) -> dict[str, list[PricePoint]]:
        return _scan.load_adjusted_series(self._base_dir, as_of=as_of)

    def full_series(self) -> dict[str, list[PricePoint]]:
        if self._full is None:
            self._full = _scan.load_adjusted_series(self._base_dir, as_of=None)
        return self._full

    def load_range(
        self, *, tickers: set[str], start: date, end: date
    ) -> dict[str, list[PricePoint]]:
        # 종목집합 × [start,end] 만 로드(메모리 절감 — full_series 전체 OOM 회피). _scan 위임.
        return _scan.load_range_series(self._base_dir, tickers, start, end)

    def tickers_with_data(self, *, tickers: set[str], start: date, end: date) -> set[str]:
        # 멤버십만(DISTINCT ticker·load_range 동일 WHERE) — PricePoint 미물질화. _scan 위임.
        return _scan.load_tickers_with_data(self._base_dir, tickers, start, end)

    def trading_days(self) -> list[date]:
        # full_series 전체 메모리 로드(OOM) 대신 DuckDB DISTINCT 집계(_scan.load_trading_days).
        return _scan.load_trading_days(self._base_dir)

    def ticker_exchanges(self) -> dict[str, Exchange]:
        return _scan.load_ticker_exchanges(self._base_dir)


class DuckDBPriceSeriesPort:
    """cache.duckdb 단일 컬럼 table → PriceSeriesPort + MomentumScorePort(ADR-007·라이브 가속).

    read_only 연결을 1회 열어 재사용(S6-a critic C2 — 매 호출 connect 금지). 핫패스 = load_range·
    momentum_scores(끝점/구간만 SQL 스캔·1억행 풀로드 회피). 결과는 ParquetPriceSeriesPort·
    momentum_universe(load_range) 와 **bit-identical**(adjusted=close*adj_factor Python 곱·windowed
    wn 기준·Task5 회귀 봉인). ⚠️ `ticker_exchanges` 만 Parquet 위임 — exchange 는 hive 파티션 키라
    cache table(build_cache SELECT)에 없다(메타·핫패스 아님). 호출부는 끝나면 `close()`.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._con = duckdb_cache.connect_readonly(base_dir)

    def close(self) -> None:
        """read_only 연결 해제(팩토리/백테스트 종료 시 호출)."""
        self._con.close()

    def load(self, *, as_of: date) -> dict[str, list[PricePoint]]:
        rows = self._con.execute(_SQL_LOAD_AS_OF, {"a": as_of}).fetchall()
        return _series_from_price_rows(rows)

    def full_series(self) -> dict[str, list[PricePoint]]:
        # 전구간(대용량) — 소규모 폴백·테스트용(Protocol 규약). 핫패스는 load_range.
        logger.warning("DuckDBPriceSeriesPort.full_series 전체 table 로드 — 핫패스면 load_range")
        rows = self._con.execute(_SQL_LOAD_ALL).fetchall()
        return _series_from_price_rows(rows)

    def load_range(
        self, *, tickers: set[str], start: date, end: date
    ) -> dict[str, list[PricePoint]]:
        if not tickers:
            return {}
        rows = self._con.execute(
            _SQL_LOAD_RANGE, {"t": list(tickers), "s": start, "e": end}
        ).fetchall()
        return _series_from_price_rows(rows)

    def tickers_with_data(self, *, tickers: set[str], start: date, end: date) -> set[str]:
        # 멤버십만(DISTINCT ticker·load_range 동일 WHERE) — 3.65M PricePoint 물질화 회피.
        if not tickers:
            return set()
        rows = self._con.execute(
            _SQL_TICKERS_WITH_DATA, {"t": list(tickers), "s": start, "e": end}
        ).fetchall()
        out: set[str] = set()
        for row in rows:
            (ticker,) = row
            if not isinstance(ticker, str):
                msg = f"예상치 못한 ticker 타입: {type(ticker).__name__}"
                raise TypeError(msg)
            out.add(ticker)
        return out

    def trading_days(self) -> list[date]:
        rows = self._con.execute(_SQL_TRADING_DAYS).fetchall()
        out: list[date] = []
        for row in rows:
            (td,) = row
            if not isinstance(td, date):
                msg = f"예상치 못한 trade_date 타입: {type(td).__name__}"
                raise TypeError(msg)
            out.append(td)
        return out

    def ticker_exchanges(self) -> dict[str, Exchange]:
        # exchange 는 cache table 에 없음(hive 파티션) → Parquet 위임. 메타·핫패스 아님.
        return _scan.load_ticker_exchanges(self._base_dir)

    def momentum_scores(
        self,
        *,
        tickers: set[str],
        as_of: date,
        lookback_days: int,
        skip_recent_days: int,
    ) -> dict[str, MomentumScore]:
        if not tickers:
            return {}
        window_days = momentum_window_days(lookback_days, skip_recent_days)
        eps = duckdb_cache.momentum_endpoints(
            self._con,
            tickers=tickers,
            as_of=as_of,
            lookback_days=lookback_days,
            skip_recent_days=skip_recent_days,
            window_days=window_days,
        )
        out: dict[str, MomentumScore] = {}
        for ticker, e in eps.items():
            end_pt = (
                _scan.PricePoint(trade_date=e.end_date, adjusted=e.end_adjusted)
                if e.end_date is not None and e.end_adjusted is not None
                else None
            )
            start_pt = (
                _scan.PricePoint(trade_date=e.start_date, adjusted=e.start_adjusted)
                if e.start_date is not None and e.start_adjusted is not None
                else None
            )
            out[ticker] = factors.momentum_from_endpoints(
                end_point=end_pt,
                start_point=start_pt,
                end_idx=e.end_idx,
                start_idx=e.start_idx,
                lookback_days=lookback_days,
            )
        return out


class PriceDerivedUniverse:
    """가격 존재로 유니버스 도출 — listed=첫 거래일, 폐지 없음. ⚠️ survivorship 한계(실폐지 미반영).

    골격(무료) 전용 차선: 종목마스터(listed/delisted) 부재 시 가격 시계열의 첫 거래일을 상장일로
    간주한다. 미래상장 배제·실폐지 청산은 못 하므로(data_caveats 고지), 결제 후 종목마스터 기반
    UniversePort 로 교체한다. UniversePort Protocol(constituents·delisting_event) 구현.
    """

    def __init__(self, price_port: PriceSeriesPort) -> None:
        self._listed = {
            ticker: pts[0].trade_date for ticker, pts in price_port.full_series().items() if pts
        }

    def constituents(self, *, as_of: date) -> set[str]:
        return {ticker for ticker, listed_at in self._listed.items() if listed_at <= as_of}

    def delisting_event(self, ticker: str) -> date | None:  # noqa: ARG002 (가격기반엔 폐지 정보 없음)
        return None

    def ticker_count(self) -> int:
        """도출된 종목 수(데모 top_n·리포트용)."""
        return len(self._listed)


class MasterUniverse:
    """종목마스터 스냅샷(`stock_snapshot.json`) 기반 시점 유니버스 — 생존편향+룩어헤드-correct.

    `constituents(as_of)` = `listed_at<=as_of AND (boundary None OR as_of<boundary)`
    — FakeUniversePort 와 **동일 규약**(`as_of<boundary`)이되 **입력 의미가 다르다**: Fake 의
    `delisted` 인자는 이미 "첫 거래불가일"이고, 스냅샷 `delisted_at`(마지막 실거래일)은 `+1day`
    변환 후 그 규약에 들어간다(같은 boundary 를 주면 동일 결과 — formula 동일이 아님·`+1day` 제거
    금지). ⚠️ **경계 변환(BLOCKING)**: 스냅샷
    `delisted_at`=마지막 실거래일(추정)인데 engine/Fake/Protocol 은 경계를 "첫 거래불가일"로
    해석(`_price_before(de)`=de 직전 마지막 봉) → 로드 시 `boundary = delisted_at + 1day` 로
    변환해야 마지막 실거래일이 거래가능으로 유지되고(constituents) 청산가가 마지막 실봉이 된다
    (`delisting_event`=boundary → engine `_price_before(boundary)`=마지막 실봉). engine/ports/
    fakes 불변 — 변환은 이 어댑터 내부에만.

    ⚠️ `listed_at None`(가격 없는 마스터 종목)·degenerate(`listed_at>=delisted_at`) 행은 제외
    (조용한 소실 금지 — degenerate 는 WARNING). UniversePort Protocol 구현.
    """

    def __init__(self, base_dir: Path) -> None:
        payload = json.loads((base_dir / _SNAPSHOT_NAME).read_text(encoding="utf-8"))
        self._membership: dict[str, tuple[date, date | None]] = {}
        dropped = no_price = 0
        for s in payload["stocks"]:
            # 외부 입력(JSON) 경계 검증 — isinstance 로 Any 흐름 차단(python-conventions §타입).
            ticker = str(s["ticker"])
            listed_raw = s["listed_at"]
            if not isinstance(listed_raw, str):
                no_price += 1  # listed_at 부재(가격 없는 마스터 종목) — 거래 불가, 제외(방어적)
                continue
            delisted_raw = s["delisted_at"]
            listed = date.fromisoformat(listed_raw)
            delisted = date.fromisoformat(delisted_raw) if isinstance(delisted_raw, str) else None
            if delisted is not None and listed >= delisted:
                dropped += 1  # degenerate(하루도 거래 불가) — 조용한 소실 금지
                continue
            boundary = delisted + timedelta(days=1) if delisted is not None else None
            self._membership[ticker] = (listed, boundary)
        self._dropped_degenerate = dropped  # 관측성 — 호출부/테스트가 읽어 caveat 반영 가능
        if dropped:
            logger.warning("MasterUniverse degenerate(listed>=delisted) %d종목 제외", dropped)
        if no_price:
            logger.info("MasterUniverse listed_at 부재 %d종목 제외(가격 없는 마스터)", no_price)

    def constituents(self, *, as_of: date) -> set[str]:
        return {
            ticker
            for ticker, (listed, boundary) in self._membership.items()
            if listed <= as_of and (boundary is None or as_of < boundary)
        }

    def delisting_event(self, ticker: str) -> date | None:
        m = self._membership.get(ticker)
        return m[1] if m is not None else None

    def ticker_count(self) -> int:
        """유니버스 멤버십 종목 수(데모 top_n·리포트용)."""
        return len(self._membership)


def _select_universe(base_dir: Path, price_port: PriceSeriesPort) -> UniversePort:
    """스냅샷 존재 시 MasterUniverse(생존편향-correct)·부재 시 PriceDerivedUniverse(골격 폴백).

    ⚠️ 부재→폴백은 WARNING(생존편향 미방어 상태가 조용히 지속되는 anti-pattern 방지).
    """
    if (base_dir / _SNAPSHOT_NAME).is_file():
        logger.info("유니버스=MasterUniverse(stock_snapshot.json·생존편향-correct 멤버십)")
        return MasterUniverse(base_dir)
    logger.warning(
        "유니버스=PriceDerivedUniverse 폴백 — stock_snapshot.json 부재(생존편향 미방어·골격). "
        "MasterUniverse 쓰려면 `bulk --finalize` 로 스냅샷 생성"
    )
    return PriceDerivedUniverse(price_port)


def _select_price_port(base_dir: Path) -> PriceSeriesPort:
    """cache.duckdb 있으면 DuckDBPriceSeriesPort(가속)·없거나 부패면 ParquetPriceSeriesPort 폴백.

    ⚠️ 폴백은 **기능 회귀 0**(결과 동일·속도만 캐시 의존). 부재→WARNING(가속 안 됨·`bulk --finalize`
    로 빌드 안내), 부패(연결 실패)→exception 로그 후 Parquet 폴백(반쪽 .duckdb 가 백테스트를 막지
    않게). 호출부는 끝나면 `_close_price_port`(DuckDB 연결 해제·Parquet no-op).
    """
    if not duckdb_cache.cache_exists(base_dir):
        logger.warning(
            "가격포트=ParquetPriceSeriesPort 폴백 — cache.duckdb 부재(속도 미가속). "
            "`bulk --finalize` 로 빌드하면 DuckDBPriceSeriesPort 가속"
        )
        return ParquetPriceSeriesPort(base_dir)

    import duckdb

    try:
        port = DuckDBPriceSeriesPort(base_dir)
    except (duckdb.Error, OSError):
        logger.exception("cache.duckdb 연결 실패(부패 가능) — ParquetPriceSeriesPort 폴백")
        return ParquetPriceSeriesPort(base_dir)
    logger.info("가격포트=DuckDBPriceSeriesPort(cache.duckdb·라이브 가속·ADR-007)")
    return port


def _close_price_port(port: PriceSeriesPort) -> None:
    """DuckDBPriceSeriesPort read_only 연결 해제(Parquet 포트는 no-op). 호출부 finally 에서 사용."""
    if isinstance(port, DuckDBPriceSeriesPort):
        port.close()
