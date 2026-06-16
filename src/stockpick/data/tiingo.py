"""Tiingo EOD 가격 어댑터 — `DataSource` Protocol 구현(B-pipeline 1~3단계).

진실 원천(추측·기억 금지): `docs/apis/tiingo/end-of-day.json`(가격) ·
`general-connecting.json`(인증) · `utilities-search.json`(검색). 엔드포인트·파라미터·응답필드는
캡처된 명세 그대로만 사용한다(api-spec-reference 규칙).

모듈 경계(python-conventions): `data` 는 `rules`/`backtest`/상위(api·webapp)를 import 하지
않는다. 도메인 계약(`..types`)과 인터페이스(`.source`)만 의존한다.

수정주가 BLOCKING: 응답의 raw OHLCV 를 원본 그대로 `DailyBar` 에 담고(원본 불변), 수정주가는
공유 헬퍼 `_adjust.compute_adj_factor(adjClose, close)` 로 산출해 보관한다(adjusted = raw *
adj_factor). float 금지 — Decimal 정밀(부동소수 오차로 수익률 왜곡 방지). 산출 정밀도는 헬퍼가
의도 정밀도(소수 12자리)로 quantize 한다(나눗셈 무한소수 꼬리 제거 — TASK-C). 결측·거래정지는
추측 채움 없이 누락 행으로 둔다.

생존편향 BLOCKING: Tiingo 무료 플랜은 폐지종목 survivorship-free 유니버스를 제공하지 않는다.
`utilities-search` 엔드포인트는 검색어 기반이며 전체 종목 나열(limit·페이지네이션) 수단이 명세에
없으므로(`docs/apis/tiingo/utilities-search.json` caveats), `iter_universe` 는 전체 유니버스를
구성할 수 없다 — 조용히 빈 리스트를 반환하지 않고 `NotImplementedError` 로 명확히 사유를 알린다.
파일럿은 `fetch_daily_bars` 중심이며, 본격 유니버스는 Sharadar SEP(M2)로 보강한다(ADR-002).
"""

from __future__ import annotations

import logging
import os
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final

import httpx

from ..types import DailyBar
from ._adjust import compute_adj_factor

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..types import Stock

logger = logging.getLogger(__name__)

_BASE_URL: Final = "https://api.tiingo.com"
_SOURCE_LABEL: Final = "tiingo"
_API_KEY_ENV: Final = "TIINGO_API_KEY"
_DEFAULT_TIMEOUT: Final = 30.0
_RATE_LIMIT_STATUS: Final = 429


class TiingoError(RuntimeError):
    """Tiingo 어댑터 기반 예외. 모든 하위 예외는 메시지에 API 키를 절대 담지 않는다."""


class TiingoAuthError(TiingoError):
    """인증 실패 — 키 미설정(`TIINGO_API_KEY`) 또는 401/403. (키 값은 메시지에 노출 안 함.)"""


class TiingoRateLimitError(TiingoError):
    """rate limit 초과(HTTP 429). Tiingo 는 시간당/일일(EST 자정 리셋)/월 대역폭 기준 —

    분·초 단위 제한이 아니므로(api-spec-reference), 호출부는 체크포인트·재시도로 한도 내 운영한다.
    재시도 가능 시점 힌트(Retry-After)가 응답에 있으면 `retry_after_seconds` 로 전달한다.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class TiingoResponseError(TiingoError):
    """4xx/5xx(429·401·403 제외) 또는 응답 파싱 실패. status_code 로 분류 가능."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TiingoSource:
    """Tiingo EOD 가격 소스 어댑터(`DataSource` Protocol 구현).

    인증 토큰은 **호출 시점**에 `os.environ[TIINGO_API_KEY]` 에서 읽는다(import 시점 아님 —
    테스트 모킹·키 회전 대응). 키는 로깅·예외 메시지·`repr` 어디에도 노출하지 않는다(logging-rules).

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

    def _auth_headers(self) -> dict[str, str]:
        """호출 시점 환경변수에서 토큰을 읽어 인증 헤더 구성.

        ⚠️ `Authorization: Token <KEY>` — Bearer 아님(general-connecting 명세). 키 미설정 시
        `TiingoAuthError`(키 값 비노출). 헤더 dict 는 외부로 반환·로깅하지 않는다(키 누설 차단).
        """
        api_key = os.environ.get(_API_KEY_ENV)
        if not api_key:
            raise TiingoAuthError(
                f"환경변수 {_API_KEY_ENV} 가 설정되지 않았습니다. "
                "Tiingo API 키를 .env 에 설정하세요."
            )
        return {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }

    def iter_universe(self, *, include_delisted: bool = True) -> list[Stock]:
        """⚠️ Tiingo 무료 플랜으로는 전체 종목 유니버스를 나열할 수 없다 — `NotImplementedError`.

        명세상(`docs/apis/tiingo/utilities-search.json`) `utilities/search` 는 검색어
        (ticker/name) 기반이며 전체 나열을 위한 limit·페이지네이션·"모든 티커" 수단이 없다.
        supported_tickers ZIP 같은 일괄 다운로드 엔드포인트도 캡처된 명세에 없다. 따라서 전체
        유니버스(특히 폐지종목 포함)를 구성할 수단이 부재하다.

        생존편향 BLOCKING: 여기서 현 상장분만 임의 반환하면 폐지종목이 조용히 누락되어 백테스트가
        무효가 된다. 그래서 빈 리스트로 눙치지 않고 명시적으로 실패한다. 본격 유니버스는 Sharadar
        SEP(M2)로 보강한다. 파일럿은 알려진 ticker 리스트로 `fetch_daily_bars` 를 직접 호출한다.

        검색을 통한 종목 식별이 필요하면 별도 `search_assets()` 사용(폐지여부 `isActive` 포함).
        """
        raise NotImplementedError(
            "Tiingo 어댑터는 전체 종목 유니버스 나열을 지원하지 않습니다(무료 플랜·명세 한계): "
            "utilities/search 는 검색어 기반이고 전체 나열용 limit/페이지네이션 수단이 명세에 "
            "없으며, supported_tickers 일괄 다운로드 엔드포인트도 캡처된 명세에 없습니다"
            f"(include_delisted={include_delisted}). 생존편향 회피를 위해 빈 결과로 조용히 "
            "누락하지 않고 명시적으로 실패합니다 — 전체 유니버스(폐지종목 포함)는 Sharadar "
            "SEP(M2)로 보강하고, 파일럿은 fetch_daily_bars 를 알려진 ticker 리스트로 직접 "
            "호출하세요. 검색이 필요하면 search_assets() 를 쓰세요."
        )

    def fetch_daily_bars(
        self,
        ticker: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[DailyBar]:
        """단일 ticker 의 EOD 일봉을 [start, end] 구간으로 조회.

        `GET /tiingo/daily/{ticker}/prices` (end-of-day 명세). start/end=None 이면 소스 제공 구간.
        응답 각 행을 `DailyBar`(raw OHLCV + adj_factor=adjClose/close)로 변환. 빈 응답(데이터
        없음)은 빈 리스트(추측 채움 금지). 룩어헤드 방지(trade_date <= t)는 호출부 책임 — 이
        계약은 구간 필터만.
        """
        params: dict[str, str] = {}
        if start is not None:
            params["startDate"] = start.isoformat()
        if end is not None:
            params["endDate"] = end.isoformat()
        # 명세 기본 format=json(메타데이터 포함). 명시해 의도 고정.
        params["format"] = "json"

        path = f"/tiingo/daily/{ticker}/prices"
        rows = self._get_json_array(path, params=params, ticker=ticker)

        bars: list[DailyBar] = []
        for row in rows:
            bar = self._row_to_bar(row, ticker=ticker)
            if bar is not None:
                bars.append(bar)
        logger.info(
            "Tiingo EOD 조회 완료: ticker=%s, rows=%d, bars=%d, start=%s, end=%s",
            ticker,
            len(rows),
            len(bars),
            start,
            end,
        )
        return bars

    def search_assets(self, query: str) -> list[dict[str, object]]:
        """티커/이름으로 자산 검색(`/tiingo/utilities/search`). 응답 raw dict 리스트 반환.

        명세상 응답에 `isActive`(폐지=false) 가 있어 폐지여부 식별에 쓸 수 있으나, 이 엔드포인트는
        전체 유니버스 나열 수단이 아니다(검색어 필요·limit 미기재). 따라서 raw 그대로 반환하고
        `Stock` 매핑은 호출부 판단에 맡긴다(필드 placeholder permaTicker/openFIGI 는 명세상 미구현).
        """
        path = f"/tiingo/utilities/search/{query}"
        return self._get_json_array(path, params={}, ticker=query)

    # ----- 내부 HTTP/파싱 헬퍼 -----

    def _get_json_array(
        self,
        path: str,
        *,
        params: Mapping[str, str],
        ticker: str,
    ) -> list[dict[str, object]]:
        """공통 GET → JSON 배열. 에러를 status 별로 분류해 명확히 보고(키 비노출)."""
        headers = self._auth_headers()
        url = f"{_BASE_URL}{path}"
        try:
            if self._client is not None:
                response = self._client.get(url, params=params, headers=headers)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            # 키는 헤더에만 실리고 url/params 엔 없음(헤더는 로깅 안 함) — 예외 메시지엔 path만.
            raise TiingoResponseError(
                f"Tiingo 요청 타임아웃: ticker={ticker}, path={path}"
            ) from exc
        except httpx.HTTPError as exc:
            raise TiingoResponseError(
                f"Tiingo 요청 전송 실패: ticker={ticker}, path={path}"
            ) from exc

        self._raise_for_status(response, ticker=ticker, path=path)

        try:
            payload: object = response.json()
        except ValueError as exc:
            raise TiingoResponseError(
                f"Tiingo 응답이 JSON 이 아닙니다: ticker={ticker}, path={path}",
                status_code=response.status_code,
            ) from exc

        if not isinstance(payload, list):
            raise TiingoResponseError(
                f"Tiingo 응답이 배열이 아닙니다(type={type(payload).__name__}): "
                f"ticker={ticker}, path={path}",
                status_code=response.status_code,
            )
        # 각 원소가 dict 인지 경계 검증(추측 금지)
        result: list[dict[str, object]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise TiingoResponseError(
                    f"Tiingo 응답 원소가 객체가 아닙니다(type={type(item).__name__}): "
                    f"ticker={ticker}, path={path}",
                    status_code=response.status_code,
                )
            result.append(item)
        return result

    def _raise_for_status(self, response: httpx.Response, *, ticker: str, path: str) -> None:
        """HTTP status 분류 — 429/401·403/기타 4xx·5xx. 응답 본문·헤더에 키가 없으니 안전."""
        status = response.status_code
        if status == _RATE_LIMIT_STATUS:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            logger.warning(
                "Tiingo rate limit(429): ticker=%s, path=%s, retry_after=%s",
                ticker,
                path,
                retry_after,
            )
            raise TiingoRateLimitError(
                f"Tiingo rate limit 초과(429): ticker={ticker}, path={path}. "
                "시간당/일일 한도 — 체크포인트·재시도로 한도 내 운영하세요.",
                retry_after_seconds=retry_after,
            )
        if status in (401, 403):
            # ⚠️ 키 값은 절대 메시지에 넣지 않는다.
            raise TiingoAuthError(
                f"Tiingo 인증 거부(HTTP {status}): ticker={ticker}, path={path}. "
                f"{_API_KEY_ENV} 가 유효한지 확인하세요."
            )
        if status >= 400:
            raise TiingoResponseError(
                f"Tiingo 응답 오류(HTTP {status}): ticker={ticker}, path={path}",
                status_code=status,
            )

    def _row_to_bar(self, row: Mapping[str, object], *, ticker: str) -> DailyBar | None:
        """응답 1행 → DailyBar. 필수 필드 결측·파싱 불가 시 WARNING 후 누락(추측 채움 금지)."""
        raw_date = row.get("date")
        trade_date = _parse_date(raw_date)
        if trade_date is None:
            logger.warning(
                "Tiingo 행 date 결측/파싱불가 — 누락: ticker=%s, raw_date=%r", ticker, raw_date
            )
            return None

        open_ = _to_decimal(row.get("open"))
        high = _to_decimal(row.get("high"))
        low = _to_decimal(row.get("low"))
        close = _to_decimal(row.get("close"))
        volume = _to_int(row.get("volume"))
        if open_ is None or high is None or low is None or close is None or volume is None:
            logger.warning("Tiingo 행 OHLCV 결측 — 누락: ticker=%s, date=%s", ticker, trade_date)
            return None

        adj_close = _to_decimal(row.get("adjClose"))
        adj_factor = compute_adj_factor(
            adj_close, close, source=_SOURCE_LABEL, ticker=ticker, trade_date=trade_date
        )

        return DailyBar(
            ticker=ticker,
            trade_date=trade_date,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            value=None,  # Tiingo EOD 응답에 거래대금($) 필드 없음(명세) — 추측 산출 금지
            adj_factor=adj_factor,
        )


def _parse_retry_after(value: str | None) -> float | None:
    """Retry-After 헤더(초 단위 정수만 처리; HTTP-date 형식은 None)."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_date(value: object) -> date | None:
    """Tiingo date 문자열 → date. ISO 또는 'YYYY-MM-DDT...' 타임스탬프 모두 앞 10자로 파싱."""
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
