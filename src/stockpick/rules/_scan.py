"""Parquet → ticker별 수정주가 시계열 로드 — 룰엔진의 데이터 진입(DuckDB 스캔, 룩어헤드 1차 가드).

랭킹·팩터 계산의 입력은 **수정주가(adjusted) 시계열**이다(types.DailyBar 모델: adjusted = close *
adj_factor, 원본 불변). 배당·분할 점프를 보정한 adjusted 로 수익률을 계산해야 모멘텀이 왜곡되지
않는다(python-conventions §금융: 수정주가 BLOCKING). 이 모듈은 `data/parquet` 트리를 DuckDB 로
스캔해 ticker별 `(trade_date, adjusted)` 시계열을 만든다.

⚠️ 룩어헤드 BLOCKING(1차 방어선): `as_of` 가 주어지면 **SQL WHERE 절에서 `trade_date <= as_of`**
로 필터해 미래 행이 애초에 메모리로 들어오지 못하게 한다. 팩터 계산(factors.py)이 2차 방어선으로
다시 필터하지만, 데이터 경계에서 먼저 차단하는 게 가장 안전하다. as_of=None 이면 전체 구간
(백테스트 아닌 단발 최신 산출용 — 이 경우에도 "데이터에 미래가 없다"는 호출부 책임).

모듈 경계(python-conventions): `rules` 는 `data`·`..types` 만 의존하고 `backtest`/상위(api·webapp)를
import 하지 않는다. 저장 레이아웃(Hive 파티션 daily_bar)은 data.storage 와 동일 규약을 읽기만 한다
(쓰기는 data 책임 — 여기선 읽기 전용 스캔).

Java 비유: read-only 리포지토리의 조회 메서드 — Parquet 을 테이블처럼 보고 SELECT ... WHERE
trade_date <= :asOf ORDER BY trade_date 로 종목별 시계열을 꺼내는 것과 같다. ORM 대신 DuckDB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from ..types import Exchange

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

logger = logging.getLogger(__name__)

_DATASET_NAME: Final = "daily_bar"

# 수정주가 시계열 조회 SQL. SQL 골격은 코드 리터럴, 경로/as_of 는 파라미터 바인딩($glob,$as_of)
# 으로만 주입(사용자 입력이 SQL 에 안 섞임 — storage.py 동일 규약). adjusted = close * adj_factor.
_FROM: Final = "FROM read_parquet($glob, hive_partitioning=true)"
# as_of 필터 있음: trade_date <= as_of (룩어헤드 1차 가드). 없음: 전체.
_SQL_SERIES_AS_OF: Final = (  # noqa: S608
    f"SELECT ticker, trade_date, close, adj_factor {_FROM} "
    f"WHERE trade_date <= $as_of ORDER BY ticker, trade_date"
)
_SQL_SERIES_ALL: Final = (  # noqa: S608
    f"SELECT ticker, trade_date, close, adj_factor {_FROM} ORDER BY ticker, trade_date"
)
# ticker → exchange 매핑. exchange 는 Hive 파티션 키(디렉토리)라 read_parquet 가 컬럼으로 노출.
# 한 ticker 가 여러 exchange 파티션에 있으면 거래소 이전 이력(드묾)이므로 max 로 단일화(데모
# 단순화 — 시점별 거래소 이력은 M2+ ticker_history 책임). GROUP BY 로 (ticker, exchange) 쌍만.
_SQL_TICKER_EXCHANGE: Final = (  # noqa: S608
    f"SELECT ticker, max(exchange) {_FROM} GROUP BY ticker ORDER BY ticker"
)
# ticker → as_of 이하 최신 거래일의 raw close(명목 시장가). arg_max(close, trade_date) = 최신가.
# ⚠️ raw(미수정) — P/B 분자는 명목가라야 명목 장부가와 일관(adjusted 는 명목 P/B 왜곡).
_SQL_CLOSE_AS_OF: Final = (  # noqa: S608
    f"SELECT ticker, arg_max(close, trade_date) {_FROM} "
    f"WHERE trade_date <= $as_of GROUP BY ticker ORDER BY ticker"
)
_SQL_CLOSE_ALL: Final = (  # noqa: S608
    f"SELECT ticker, arg_max(close, trade_date) {_FROM} GROUP BY ticker ORDER BY ticker"
)


@dataclass(frozen=True, slots=True)
class PricePoint:
    """수정주가 시계열의 한 점 — (trade_date, adjusted). adjusted = raw close * adj_factor.

    가격은 Decimal(정밀도 BLOCKING — float 금지, 부동소수 오차로 수익률 왜곡 방지). 팩터 계산은
    이 adjusted 만 본다(raw·adj_factor 는 스캔 단계에서 합성 완료 — 하류는 수정주가만 다룬다).
    """

    trade_date: date
    adjusted: Decimal


def load_adjusted_series(
    base_dir: Path,
    *,
    as_of: date | None = None,
) -> dict[str, list[PricePoint]]:
    """Parquet 트리 → ticker별 수정주가 시계열(trade_date 오름차순). 룩어헤드 1차 가드 포함.

    반환: {ticker: [PricePoint(...), ...]} — 각 리스트는 trade_date 오름차순. adjusted = close *
    adj_factor 를 DuckDB 에서 합성한다(원본 불변 — raw 는 읽되 변형 안 함).

    ⚠️ as_of 가 주어지면 `trade_date <= as_of` 행만 로드한다(룩어헤드 BLOCKING 1차 방어선 — 미래
    행이 메모리에 들어오지 않음). as_of=None 이면 전체 구간(단발 최신 산출 — 미래 부재는 호출부
    책임). 트리가 비어 있으면 빈 맵(no-op — 조용한 추측 채움 금지).

    모듈 경계: 읽기 전용. data.storage 의 daily_bar Hive 레이아웃을 스캔만 한다.
    """
    dataset_root = base_dir / _DATASET_NAME
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        logger.warning("스캔 대상 Parquet 없음 — 빈 시계열: dataset=%s", dataset_root)
        return {}

    import duckdb

    glob = f"{dataset_root}/**/*.parquet"
    params: dict[str, object] = {"glob": glob}
    if as_of is not None:
        sql = _SQL_SERIES_AS_OF
        params["as_of"] = as_of
    else:
        sql = _SQL_SERIES_ALL

    con = duckdb.connect(database=":memory:")
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()

    series: dict[str, list[PricePoint]] = {}
    for ticker, trade_date, close, adj_factor in _iter_rows(rows):
        adjusted = close * adj_factor
        series.setdefault(ticker, []).append(PricePoint(trade_date=trade_date, adjusted=adjusted))

    logger.info(
        "수정주가 시계열 로드: tickers=%d, as_of=%s, total_points=%d",
        len(series),
        as_of if as_of is not None else "(전체)",
        sum(len(v) for v in series.values()),
    )
    return series


def load_close_as_of(base_dir: Path, *, as_of: date | None = None) -> dict[str, Decimal]:
    """Parquet 트리 → {ticker: as_of 이하 최신 거래일의 raw close}. P/B 분자(명목 시장가)용.

    ⚠️ raw close(미수정) 반환 — 수정주가(adjusted) 아님. P/B = 시장가/BVPS 는 **명목가** 기준이라야
    명목 장부가(equity/shares)와 일관(adjusted 는 back-adjust 라 명목 P/B 왜곡). 룩어헤드
    1차 가드: `trade_date <= as_of` 의 최신(arg_max(close, trade_date)). as_of=None 이면 전체 최신.
    빈 트리면 빈 맵(조용한 추측 채움 금지). 모듈 경계: 읽기 전용 스캔.
    """
    dataset_root = base_dir / _DATASET_NAME
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        logger.warning("close 스캔 대상 Parquet 없음 — 빈 맵: dataset=%s", dataset_root)
        return {}

    import duckdb

    glob = f"{dataset_root}/**/*.parquet"
    params: dict[str, object] = {"glob": glob}
    if as_of is not None:
        sql = _SQL_CLOSE_AS_OF
        params["as_of"] = as_of
    else:
        sql = _SQL_CLOSE_ALL

    con = duckdb.connect(database=":memory:")
    try:
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()

    mapping: dict[str, Decimal] = {}
    for row in rows:
        ticker, close = row
        if not (isinstance(ticker, str) and isinstance(close, Decimal)):
            msg = f"예상치 못한 close 행 타입: ticker={type(ticker)}, close={type(close)}"
            raise TypeError(msg)
        mapping[ticker] = close
    logger.info("raw close 로드: tickers=%d, as_of=%s", len(mapping), as_of or "(전체)")
    return mapping


def load_ticker_exchanges(base_dir: Path) -> dict[str, Exchange]:
    """Parquet 트리 → {ticker: Exchange}. Hive 파티션 키(exchange)를 읽어 거래소 매핑 복원.

    랭킹의 거래소별 그룹핑·TopEntry.exchange 채움에 쓴다. 저장된 exchange 문자열을 도메인 Exchange
    enum 으로 좁힌다 — 알 수 없는 값이면 추측 매핑 금지, 명시적 실패(실패 명확 보고). 빈 트리면
    빈 맵.
    """
    dataset_root = base_dir / _DATASET_NAME
    files = sorted(str(p) for p in dataset_root.rglob("*.parquet"))
    if not files:
        logger.warning("거래소 매핑 스캔 대상 없음 — 빈 맵: dataset=%s", dataset_root)
        return {}

    import duckdb

    glob = f"{dataset_root}/**/*.parquet"
    con = duckdb.connect(database=":memory:")
    try:
        rows = con.execute(_SQL_TICKER_EXCHANGE, {"glob": glob}).fetchall()
    finally:
        con.close()

    mapping: dict[str, Exchange] = {}
    for row in rows:
        ticker, exchange_str = row
        if not (isinstance(ticker, str) and isinstance(exchange_str, str)):
            msg = (
                f"예상치 못한 거래소 매핑 행 타입: "
                f"ticker={type(ticker)}, exchange={type(exchange_str)}"
            )
            raise TypeError(msg)
        try:
            mapping[ticker] = Exchange(exchange_str)
        except ValueError as exc:
            # 추측 매핑 금지 — 알 수 없는 거래소 문자열은 명시적 실패(어느 ticker·값인지 보고).
            msg = (
                f"알 수 없는 거래소 값 '{exchange_str}'(ticker={ticker}) — Exchange enum 에 없음. "
                "추측 매핑 금지(실패 명확 보고)."
            )
            raise ValueError(msg) from exc
    return mapping


def _iter_rows(rows: list[tuple[object, ...]]) -> list[tuple[str, date, Decimal, Decimal]]:
    """DuckDB fetchall 행(object 튜플)을 내부 타입으로 좁힌다(strict — Any 금지, 경계 검증).

    DuckDB 는 DECIMAL 컬럼을 Python Decimal 로, DATE 를 datetime.date 로 돌려준다(실측). 그러나
    fetchall 의 정적 타입은 느슨하므로(object) 여기서 명시적으로 좁혀 하류에 정확 타입만 흘린다.
    예상과 다른 타입이면 추측 변환 없이 실패한다(실패 명확 보고 — 조용한 캐스팅 금지).
    """
    from datetime import date as date_cls

    narrowed: list[tuple[str, date, Decimal, Decimal]] = []
    for row in rows:
        ticker, trade_date, close, adj_factor = row
        if not (
            isinstance(ticker, str)
            and isinstance(trade_date, date_cls)
            and isinstance(close, Decimal)
            and isinstance(adj_factor, Decimal)
        ):
            msg = (
                "예상치 못한 스캔 행 타입(실패 명확 보고 — 조용한 캐스팅 금지): "
                f"ticker={type(ticker)}, trade_date={type(trade_date)}, "
                f"close={type(close)}, adj_factor={type(adj_factor)}"
            )
            raise TypeError(msg)
        narrowed.append((ticker, trade_date, close, adj_factor))
    return narrowed
