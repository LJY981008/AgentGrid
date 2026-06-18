"""EODHD(EOD Historical Data) EOD 가격 어댑터 — `DataSource` Protocol 구현(TASK-D).

진실 원천(추측·기억 금지): `docs/apis/eodhd/end-of-day-historical-data.json`(가격) ·
`exchanges-api-list-of-tickers-and-trading-hours.json`(유니버스) ·
`delisted-stock-companies-data.json`(폐지 커버리지) · `_index.json`(인덱스). 엔드포인트·파라미터·
응답필드는 캡처된 명세 그대로만 사용한다(api-spec-reference 규칙).

⚠️ Tiingo 와 다른 점(명세 대조):
- **인증**: `?api_token=<KEY>` **쿼리 파라미터**(Tiingo 는 `Authorization: Token` 헤더). 토큰이
  URL 에 실리므로 URL 을 로깅·예외·repr 어디에도 그대로 노출하지 않는다 — 마스킹하거나 토큰을 뺀
  형태만 남긴다(logging-rules BLOCKING).
  ⚠️ **진입점 가드(코드화됨·G6)**: 이 어댑터의 자체 로그/예외엔 토큰을 안 남기지만, `httpx`
  라이브러리의 INFO 로거(`httpx._client`)는 토큰이 실린 완성 URL 을 로깅한다(라이브러리 동작 —
  어댑터 내부에서 끌 수 없음). → `data/__init__.py:configure_logging` 이 `httpx`·`httpcore` 를
  WARNING 으로 올려 차단하며(logging-rules: 레벨 설정은 진입점 책임), 진입점(`api/app`·edgar/ingest
  `__main__`)이 이를 호출한다. ⚠️ S5-c 벌크 진입점도 반드시 configure_logging() 호출할 것.
- **유니버스 구현 가능**: Tiingo 는 전체 나열 수단이 없어 `NotImplementedError` 였으나, EODHD 는
  `exchange-symbol-list/{EX}` 로 활성 목록을, `delisted=1` 로 폐지 목록을 별도 반환한다(한 번에
  둘 다 받는 파라미터는 명세에 없음 → 두 호출 병합). 생존편향 회피의 핵심.

수정주가 BLOCKING: 응답 raw OHLC + `adjusted_close`(split+dividend 반영) 를 받아 원본 불변으로
`DailyBar` 에 담고, 수정계수는 공유 헬퍼 `_adjust.compute_adj_factor(adjusted_close, close)` 로
산출(adjusted = raw * adj_factor). ⚠️ 명세 caveat 의 "(raw close / adjusted_close)로 역산"은 역수
표현이며, 우리 계약 불변식(adjusted = raw * adj_factor)을 지키는 분자/분모는 adjusted/raw 다(_adjust
docstring 참조). float 금지 — Decimal 정밀. 결측·거래정지는 추측 채움 없이 누락 행으로 둔다.

모듈 경계(python-conventions): `data` 는 `rules`/`backtest`/상위(api·webapp)를 import 하지 않는다.
도메인 계약(`..types`)·인터페이스(`.source`)·공유 헬퍼(`._adjust`)만 의존한다.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final

import httpx

from ..types import DailyBar, Exchange, Stock
from ._adjust import compute_adj_factor

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

_BASE_URL: Final = "https://eodhd.com/api"
_SOURCE_LABEL: Final = "eodhd"
_API_KEY_ENV: Final = "EODHD_API_KEY"
_API_TOKEN_PARAM: Final = "api_token"  # noqa: S105 — 쿼리 파라미터 *이름*(키 값 아님). 로깅 시 마스킹
_DEFAULT_TIMEOUT: Final = 30.0
_RATE_LIMIT_STATUS: Final = 429
_DEFAULT_EXCHANGE_SUFFIX: Final = "US"  # 미국 기본(명세: US 코드가 NYSE/NASDAQ/ARCA/OTC 통합)


class EodhdError(RuntimeError):
    """EODHD 어댑터 기반 예외. 모든 하위 예외는 메시지에 API 토큰을 절대 담지 않는다."""


class EodhdAuthError(EodhdError):
    """인증 실패 — 키 미설정(`EODHD_API_KEY`) 또는 401/403. (토큰 값은 메시지에 노출 안 함.)"""


class EodhdRateLimitError(EodhdError):
    """rate limit 초과(HTTP 429). EODHD 는 EOD 심볼당 1콜·일일 한도(플랜별, Free 20콜/일).

    분·초 단위가 아니라 일일/플랜 한도이므로 호출부는 체크포인트·재시도로 한도 내 운영한다.
    재시도 가능 시점 힌트(Retry-After)가 응답에 있으면 `retry_after_seconds` 로 전달한다.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class EodhdResponseError(EodhdError):
    """4xx/5xx(429·401·403 제외) 또는 응답 파싱 실패. status_code 로 분류 가능."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class EodhdSource:
    """EODHD EOD 가격 소스 어댑터(`DataSource` Protocol 구현).

    인증 토큰은 **호출 시점**에 `os.environ[EODHD_API_KEY]` 에서 읽는다(import 시점 아님 —
    테스트 모킹·키 회전 대응). ⚠️ 토큰은 쿼리 파라미터로 실리므로(헤더 아님) URL 을 그대로 로깅하면
    토큰이 노출된다 — 로깅·예외·repr 어디에도 토큰/완성 URL 을 노출하지 않는다(logging-rules).

    HTTP 클라이언트는 주입 가능(`client` 인자) — 테스트에서 `httpx.MockTransport` 를 단 클라이언트를
    넘겨 라이브 호출 없이 검증한다. 미주입 시 호출마다 컨텍스트 매니저로 생성·정리한다.
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._client = client
        self._timeout = timeout

    @property
    def name(self) -> str:
        return _SOURCE_LABEL

    def _api_token(self) -> str:
        """호출 시점 환경변수에서 토큰을 읽는다. 미설정 시 EodhdAuthError(토큰 값 비노출).

        ⚠️ 반환값은 쿼리 파라미터 값으로만 쓰이며 로깅·예외·repr 에 절대 넣지 않는다.
        """
        token = os.environ.get(_API_KEY_ENV)
        if not token:
            raise EodhdAuthError(
                f"환경변수 {_API_KEY_ENV} 가 설정되지 않았습니다. "
                "EODHD API 키를 .env 에 설정하세요."
            )
        return token

    def fetch_daily_bars(
        self,
        ticker: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[DailyBar]:
        """단일 ticker 의 EOD 일봉을 [start, end] 구간으로 조회.

        `GET /eod/{SYMBOL}` (end-of-day 명세). 심볼은 `{TICKER}.{EX}` — `_to_symbol` 정책으로 정규화
        (미국 기본 `.US`, 이미 `.EX` 가 붙어 있으면 그대로). 파라미터: `from`/`to`(YYYY-MM-DD)·
        `period=d`·`order=a`·`fmt=json`(명세). 응답 raw OHLC + `adjusted_close` → `DailyBar`
        (adj_factor=공유헬퍼(adjusted_close, close)). 빈 응답은 빈 리스트(추측 채움 금지). 룩어헤드
        방지(trade_date <= t)는 호출부 책임 — 이 계약은 구간 필터만.

        반환 `DailyBar.ticker` 은 **거래소 접미사를 뗀 원 ticker**(가격 키 일관성 — 저장층·
        ticker_history 와 정합). 심볼 변환은 요청 URL 에만 쓴다.
        """
        symbol = _to_symbol(ticker)
        params: dict[str, str] = {
            "period": "d",  # 일간(명세 기본 d, 명시해 의도 고정)
            "order": "a",  # 오름차순(오래된 것부터)
            "fmt": "json",
        }
        if start is not None:
            params["from"] = start.isoformat()
        if end is not None:
            params["to"] = end.isoformat()

        path = f"/eod/{symbol}"
        rows = self._get_json_array(path, params=params, context=symbol)

        bars: list[DailyBar] = []
        for row in rows:
            bar = self._row_to_bar(row, ticker=ticker)
            if bar is not None:
                bars.append(bar)
        logger.info(
            "EODHD EOD 조회 완료: symbol=%s, rows=%d, bars=%d, start=%s, end=%s",
            symbol,
            len(rows),
            len(bars),
            start,
            end,
        )
        return bars

    def iter_universe(self, *, include_delisted: bool = True) -> list[Stock]:
        """미국 종목 유니버스를 반환(폐지 포함이 기본 — 생존편향 회피).

        명세(exchanges-api): `GET /exchange-symbol-list/{EX}` 가 활성 티커를, `delisted=1` 이
        폐지(비활성) 티커만 반환한다. **활성+폐지를 한 번에 받는 파라미터는 명세에 없으므로**
        include_delisted=True 면 두 호출(활성 + delisted=1)을 병합한다. 미국은 통합 코드 `US`
        (NYSE/NASDAQ/ARCA/OTC 포함) 사용 — 명세 권장.

        ⚠️ 한계(조용한 빈 리스트 금지 — 명시 고지):
        - cik(SEC 안정 식별자): EODHD exchange-symbol-list 응답에 CIK 필드가 없다(명세
          response_fields: Code/Name/Country/Exchange/Currency/Type/Isin). 따라서 `Stock.cik` 는
          빈 문자열로 두고 EDGAR 매핑은 후속(id-mapping 또는 EDGAR ticker→CIK)으로 보강한다. cik 가
          조인 기준이므로 이 한계는 백테스트 착수 전 반드시 해소 대상.
        - exchange: 응답 `Exchange` 는 EODHD 거래소 코드(US 통합 등)라 우리 `Exchange` enum
          (NYSE/NASDAQ/...)으로 정확 매핑 불가한 경우가 있다 → 알 수 없으면 행을 버리지 않고
          보수적으로 OTC 로 분류한다(종목 자체는 보존 — 아래 `_map_exchange`).
        - delisted=1 응답엔 폐지일(delisted_at) 필드가 없다(명세에 미기재) → `Stock.delisted_at` 은
          "폐지 목록에서 왔다"는 사실로 비-None 표식을 둘 수 없어 None 으로 두되, 활성/폐지 출처를
          로그로 구분한다. 정확한 폐지일은 후속(개별 fundamentals/EOD 마지막 거래일)로 보강.

        include_delisted=False 면 활성만 반환(명시적 요청 시에만 — 기본은 폐지 포함).
        """
        active = self._fetch_symbol_list(delisted=False)
        stocks: list[Stock] = list(active)
        if include_delisted:
            delisted = self._fetch_symbol_list(delisted=True)
            stocks.extend(delisted)
            # 활성·폐지 목록 간 ticker 겹침 고지(조용한 중복 금지). 병합은 양쪽을 보존하므로
            # (생존편향 회피 — 같은 ticker 가 양 출처에 있으면 둘 다 남김) 중복 행이 생길 수 있고,
            # 후속 ticker_history/EDGAR 매핑 단계가 CIK 로 정규화한다. 여기선 정량 고지만.
            overlap = {s.ticker for s in active} & {s.ticker for s in delisted}
            if overlap:
                logger.warning(
                    "EODHD 유니버스: 활성·폐지 ticker 겹침 %d개(병합 시 중복 행 — CIK 정규화 "
                    "후속): 예시 %s",
                    len(overlap),
                    ", ".join(sorted(overlap)[:10]),
                )
            logger.info(
                "EODHD 유니버스: 활성=%d + 폐지=%d = %d (겹침=%d, cik 미제공 — EDGAR 매핑 후속)",
                len(active),
                len(delisted),
                len(stocks),
                len(overlap),
            )
        else:
            logger.warning(
                "EODHD 유니버스: include_delisted=False — 활성 %d개만(생존편향 위험, 명시 요청 시)",
                len(active),
            )
        return stocks

    def fetch_common_stock_universe(
        self, *, include_delisted: bool = True
    ) -> tuple[list[Stock], list[Stock]]:
        """Common Stock 유니버스를 (활성, 폐지) 분리 반환 — S5-b 종목마스터용.

        iter_universe 와 차이: (1) **Common Stock 만**(ETF/펀드/우선주 제외) (2) 활성·폐지를
        **분리**(listing_status 구분 — iter_universe 는 병합). 분류는 클라 Type 필터(`keep_types`)가
        1차·정답 보장이고, 서버 `type=common_stock` 는 페이로드 최적화(best-effort — 서버가 무시/미
        결합해도 클라 필터가 정확). 활성이 0/의심스럽게 작으면 WARNING(빈 마스터 silent 실패 방지).
        이 메서드는 EodhdSource 구체 API(DataSource Protocol 아님 — 유니버스 전수는 EODHD 만).
        """
        keep = frozenset({"common stock"})
        active = self._fetch_symbol_list(
            delisted=False, keep_types=keep, security_type="common_stock"
        )
        delisted = (
            self._fetch_symbol_list(delisted=True, keep_types=keep, security_type="common_stock")
            if include_delisted
            else []
        )
        if not active:
            logger.warning(
                "EODHD Common Stock 유니버스: 활성 0개 — 서버 type= 오작동/빈 응답 의심"
                "(빈 마스터 방지 점검 필요)"
            )
        logger.info(
            "EODHD Common Stock 유니버스: 활성=%d, 폐지=%d(include_delisted=%s)",
            len(active),
            len(delisted),
            include_delisted,
        )
        return active, delisted

    def _fetch_symbol_list(
        self,
        *,
        delisted: bool,
        keep_types: frozenset[str] | None = None,
        security_type: str | None = None,
    ) -> list[Stock]:
        """`GET /exchange-symbol-list/US` 한 호출 → `list[Stock]`. delisted=True 면 폐지만 반환.

        명세 response_fields(Code/Name/Country/Exchange/Currency/Type/Isin)만 사용. Code/Name 결측
        행은 추측 채움 없이 WARNING 후 누락(조용한 채움 금지). cik 는 미제공 → 빈 문자열.

        필터(S5-b): `keep_types`(예 {"common stock"}) 주면 응답 `Type` 정규화(`.lower()`) 비교로
        **클라 1차 필터**(항상 정확). `security_type`(예 "common_stock") 주면 서버 `type=` 쿼리에
        실어 페이로드 축소(best-effort). 둘은 다른 네임스페이스(서버=소문자언더바·클라=응답필드).
        """
        params: dict[str, str] = {"fmt": "json"}
        if delisted:
            params["delisted"] = "1"
        if security_type is not None:
            params["type"] = security_type  # 서버 최적화(best-effort) — 클라 keep_types 가 정답
        path = f"/exchange-symbol-list/{_DEFAULT_EXCHANGE_SUFFIX}"
        rows = self._get_json_array(path, params=params, context=path)

        stocks: list[Stock] = []
        dropped = 0
        type_dropped = 0
        for row in rows:
            code = row.get("Code")
            name = row.get("Name")
            if not isinstance(code, str) or not code or not isinstance(name, str):
                dropped += 1
                continue
            if keep_types is not None:
                type_val = row.get("Type")
                normalized = type_val.strip().lower() if isinstance(type_val, str) else ""
                if normalized not in keep_types:
                    type_dropped += 1
                    continue
            stocks.append(
                Stock(
                    cik="",  # EODHD 미제공 — EDGAR 매핑 후속(docstring 한계 참조)
                    ticker=code,
                    name=name,
                    exchange=_map_exchange(row.get("Exchange")),
                    listed_at=None,  # 명세에 상장일 필드 없음
                    delisted_at=None,  # 명세에 폐지일 필드 없음(출처는 로그로 구분)
                )
            )
        if dropped:
            logger.warning(
                "EODHD 심볼 목록 Code/Name 결측 %d행 누락(추측 채움 금지): delisted=%s",
                dropped,
                delisted,
            )
        if type_dropped:
            logger.info(
                "EODHD 심볼 목록 Type 필터 제외 %d행(keep=%s·delisted=%s)",
                type_dropped,
                sorted(keep_types) if keep_types else None,
                delisted,
            )
        return stocks

    # ----- 내부 HTTP/파싱 헬퍼 -----

    def _get_json_array(
        self,
        path: str,
        *,
        params: Mapping[str, str],
        context: str,
    ) -> list[dict[str, object]]:
        """공통 GET → JSON 배열. 토큰은 쿼리에 주입하되 로깅엔 절대 노출 안 함(마스킹).

        context = 로그·예외 식별용(심볼/경로 — 토큰 없음). 에러를 status 별로 분류해 명확히 보고.
        """
        token = self._api_token()
        # ⚠️ 토큰은 여기서만 쿼리에 더한다. 이후 로그·예외에 query_params/url 을 그대로 안 남긴다.
        query: dict[str, str] = {**params, _API_TOKEN_PARAM: token}
        url = f"{_BASE_URL}{path}"
        try:
            if self._client is not None:
                response = self._client.get(url, params=query)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, params=query)
        except httpx.TimeoutException:
            # from None: httpx 예외 repr 에 토큰 실린 URL 이 포함될 수 있어 체인을 끊는다.
            # 우리 메시지엔 path(토큰 없음)와 context 만 남긴다(노출 방지).
            raise EodhdResponseError(
                f"EODHD 요청 타임아웃: context={context}, path={path}"
            ) from None
        except httpx.HTTPError:
            raise EodhdResponseError(
                f"EODHD 요청 전송 실패: context={context}, path={path}"
            ) from None

        self._raise_for_status(response, context=context, path=path)

        try:
            payload: object = response.json()
        except ValueError as exc:
            raise EodhdResponseError(
                f"EODHD 응답이 JSON 이 아닙니다: context={context}, path={path}",
                status_code=response.status_code,
            ) from exc

        if not isinstance(payload, list):
            raise EodhdResponseError(
                f"EODHD 응답이 배열이 아닙니다(type={type(payload).__name__}): "
                f"context={context}, path={path}",
                status_code=response.status_code,
            )
        result: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise EodhdResponseError(
                    f"EODHD 응답 원소가 객체가 아닙니다(type={type(item).__name__}): "
                    f"context={context}, path={path}",
                    status_code=response.status_code,
                )
            result.append(item)
        return result

    def _raise_for_status(self, response: httpx.Response, *, context: str, path: str) -> None:
        """HTTP status 분류 — 429/401·403/기타 4xx·5xx. 메시지엔 토큰 비노출(path/context 만)."""
        status = response.status_code
        if status == _RATE_LIMIT_STATUS:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            logger.warning(
                "EODHD rate limit(429): context=%s, path=%s, retry_after=%s",
                context,
                path,
                retry_after,
            )
            raise EodhdRateLimitError(
                f"EODHD rate limit 초과(429): context={context}, path={path}. "
                "일일/플랜 한도 — 체크포인트·재시도로 한도 내 운영하세요.",
                retry_after_seconds=retry_after,
            )
        if status in (401, 403):
            # ⚠️ 토큰 값은 절대 메시지에 넣지 않는다.
            raise EodhdAuthError(
                f"EODHD 인증 거부(HTTP {status}): context={context}, path={path}. "
                f"{_API_KEY_ENV} 가 유효한지 확인하세요."
            )
        if status >= 400:
            raise EodhdResponseError(
                f"EODHD 응답 오류(HTTP {status}): context={context}, path={path}",
                status_code=status,
            )

    def _row_to_bar(self, row: Mapping[str, object], *, ticker: str) -> DailyBar | None:
        """응답 1행 → DailyBar. 필수 필드 결측·파싱 불가 시 WARNING 후 누락(추측 채움 금지).

        명세 response_fields: date/open/high/low/close/adjusted_close/volume. 거래대금(value) 필드는
        EODHD EOD 응답에 없음 → value=None(추측 산출 금지).
        """
        raw_date = row.get("date")
        trade_date = _parse_date(raw_date)
        if trade_date is None:
            logger.warning(
                "EODHD 행 date 결측/파싱불가 — 누락: ticker=%s, raw_date=%r", ticker, raw_date
            )
            return None

        open_ = _to_decimal(row.get("open"))
        high = _to_decimal(row.get("high"))
        low = _to_decimal(row.get("low"))
        close = _to_decimal(row.get("close"))
        volume = _to_int(row.get("volume"))
        if open_ is None or high is None or low is None or close is None or volume is None:
            logger.warning("EODHD 행 OHLCV 결측 — 누락: ticker=%s, date=%s", ticker, trade_date)
            return None

        adjusted_close = _to_decimal(row.get("adjusted_close"))
        adj_factor = compute_adj_factor(
            adjusted_close, close, source=_SOURCE_LABEL, ticker=ticker, trade_date=trade_date
        )

        return DailyBar(
            ticker=ticker,
            trade_date=trade_date,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            value=None,  # EODHD EOD 응답에 거래대금($) 필드 없음(명세) — 추측 산출 금지
            adj_factor=adj_factor,
        )


def _to_symbol(ticker: str) -> str:
    """ticker → EODHD 심볼 `{TICKER}.{EX}`. 이미 `.EX` 가 있으면 그대로, 없으면 미국 기본 `.US`.

    명세: 심볼은 거래소 코드 필수(`AAPL.US`). 정책 명확화 — ticker 에 점(.)이 이미 있으면 호출부가
    거래소를 명시한 것으로 보고 그대로 사용(예: `MCD.MX`), 없으면 미국(`.US`)을 붙인다. 빈 ticker 는
    그대로 반환해 상위 호출이 빈 심볼로 명확히 실패하게 한다(추측 보정 금지 — `.US` 부착 시 `.US`
    라는 가짜 심볼로 요청돼 실패가 흐려진다).
    """
    if not ticker:
        return ticker
    if "." in ticker:
        return ticker
    return f"{ticker}.{_DEFAULT_EXCHANGE_SUFFIX}"


# EODHD 거래소 코드 → 우리 Exchange enum. US 통합 코드는 세부 거래소 미상이라 보수적으로 매핑.
# 명세상 exchange-symbol-list 응답의 Exchange 필드는 EODHD 코드(US 등)라 NYSE/NASDAQ 구분이 안 된다.
_EXCHANGE_MAP: Final[dict[str, Exchange]] = {
    "NYSE": Exchange.NYSE,
    "NASDAQ": Exchange.NASDAQ,
    "NYSE ARCA": Exchange.NYSE_ARCA,
    "NYSE MKT": Exchange.NYSE_AMERICAN,
    "AMEX": Exchange.NYSE_AMERICAN,
    "BATS": Exchange.BATS,
    "OTC": Exchange.OTC,
    "OTCMKTS": Exchange.OTC,
    "PINK": Exchange.OTC,
}


def _map_exchange(value: object) -> Exchange:
    """EODHD 거래소 코드 → Exchange enum. 매핑 미상이면 OTC(보수적, 조용한 누락보다 보존 우선).

    ⚠️ US 통합 코드(NYSE/NASDAQ/ARCA/OTC 묶음)는 세부 거래소를 명세가 분리 제공하지 않아 정확 매핑
    불가 → OTC 로 보수 분류한다(행을 버리지 않음 — 생존편향: 종목 자체는 보존). 정확한 거래소는
    후속(개별 fundamentals 의 Exchange 또는 별도 매핑)으로 보강. None/미상도 OTC.
    """
    if isinstance(value, str):
        # _EXCHANGE_MAP 키는 전부 대문자 → upper() 조회로 충분(원본 조회는 dead code).
        mapped = _EXCHANGE_MAP.get(value.upper())
        if mapped is not None:
            return mapped
    return Exchange.OTC


def _parse_retry_after(value: str | None) -> float | None:
    """Retry-After 헤더(초 단위 정수만 처리; HTTP-date 형식은 None)."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_date(value: object) -> date | None:
    """EODHD date 문자열(YYYY-MM-DD) → date. 앞 10자로 파싱(타임스탬프 형태도 수용)."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _to_decimal(value: object) -> Decimal | None:
    """JSON 숫자/문자 → Decimal. float 는 str 경유로 정밀 보존. 결측/파싱불가 → None(추측 금지)."""
    if value is None:
        return None
    if isinstance(value, bool):  # bool 은 int 하위형 — 가격 아님, 거부
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None


def _to_int(value: object) -> int | None:
    """JSON 정수 → int. float 거래량은 정수면 수용(예: 1.0), 소수면 None. 결측 → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
