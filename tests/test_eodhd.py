"""EodhdSource 어댑터 모킹 단위 테스트 — 라이브 호출 0(httpx.MockTransport).

응답 픽스처는 `docs/apis/eodhd/end-of-day-historical-data.json` response_fields 형태 그대로
(date/open/high/low/close/adjusted_close/volume) + exchange-symbol-list(Code/Name/Exchange/...).
검증 항목: adj_factor=quantize(adjusted_close/close, 12자리) 정확·raw Decimal 보존·분할 케이스
(adjusted≠close → factor≠1)·키 미설정 에러·키(토큰) 비노출(URL 마스킹 포함)·심볼 포맷(.US 기본/명시
유지)·429·4xx 분류·iter_universe(활성+폐지 병합, cik 한계)·value=None(거래대금 필드 없음).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

import httpx
import pytest

from stockpick.data.eodhd import (
    EodhdAuthError,
    EodhdRateLimitError,
    EodhdResponseError,
    EodhdSource,
)
from stockpick.data.source import DataSource
from stockpick.types import Exchange

_FAKE_KEY = "test-token-DO-NOT-LOG"

# end-of-day-historical-data.json response_fields 형태 — 분할 없음(adjusted_close==close → factor 1)
_ROW_NO_SPLIT: dict[str, object] = {
    "date": "2024-06-03",
    "open": 192.9,
    "high": 194.99,
    "low": 192.52,
    "close": 194.03,
    "adjusted_close": 194.03,
    "volume": 50080539,
}
# 분할/배당 조정 케이스: adjusted_close < close → factor < 1
_ROW_SPLIT: dict[str, object] = {
    "date": "2020-08-31",
    "open": 127.58,
    "high": 131.0,
    "low": 126.0,
    "close": 129.04,
    "adjusted_close": 127.46,
    "volume": 225702700,
}


def _make_source(
    handler: httpx.MockTransport | None = None,
    *,
    rows: list[dict[str, object]] | None = None,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> EodhdSource:
    """MockTransport 를 단 EodhdSource — 라이브 호출 0. rows 지정 시 그 JSON 을 status 로 반환."""
    if handler is None:

        def _default(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json=rows if rows is not None else [], headers=headers)

        handler = httpx.MockTransport(_default)
    client = httpx.Client(transport=handler)
    return EodhdSource(client=client)


@pytest.fixture(autouse=True)
def _set_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """대부분 테스트는 키가 설정된 상태 가정. 키 미설정 테스트는 개별 delenv."""
    monkeypatch.setenv("EODHD_API_KEY", _FAKE_KEY)


def test_implements_datasource_protocol() -> None:
    """구조적으로 DataSource Protocol 을 만족(runtime_checkable isinstance)."""
    src = _make_source()
    assert isinstance(src, DataSource)
    assert src.name == "eodhd"


def test_fetch_daily_bars_maps_raw_ohlcv_decimal() -> None:
    """raw OHLCV 가 Decimal 로 보존되고 trade_date 가 YYYY-MM-DD 에서 파싱된다. value=None."""
    src = _make_source(rows=[_ROW_NO_SPLIT])
    bars = src.fetch_daily_bars("AAPL")
    assert len(bars) == 1
    bar = bars[0]
    assert bar.ticker == "AAPL"  # 거래소 접미사 없는 원 ticker(가격 키 일관성)
    assert bar.trade_date == date(2024, 6, 3)
    assert bar.open == Decimal("192.9")
    assert bar.close == Decimal("194.03")
    assert isinstance(bar.close, Decimal)
    assert bar.volume == 50080539
    assert bar.value is None  # EODHD EOD 에 거래대금 필드 없음 — 추측 산출 안 함


def test_adj_factor_one_when_adjusted_equals_close() -> None:
    """무분할·무배당 구간: adjusted_close==close → adj_factor==1."""
    src = _make_source(rows=[_ROW_NO_SPLIT])
    bar = src.fetch_daily_bars("AAPL")[0]
    assert bar.adj_factor == Decimal("1")


def test_adj_factor_quantized_from_adjusted_over_close_on_split() -> None:
    """분할 케이스: adj_factor = quantize(adjusted_close/close, 12자리), 1 아님. raw close 불변."""
    src = _make_source(rows=[_ROW_SPLIT])
    bar = src.fetch_daily_bars("AAPL")[0]
    expected = (Decimal("127.46") / Decimal("129.04")).quantize(
        Decimal("1E-12"), rounding=ROUND_HALF_EVEN
    )
    assert bar.adj_factor == expected
    assert bar.adj_factor != Decimal("1")
    exponent = bar.adj_factor.as_tuple().exponent  # 유한 Decimal → int(특수값 'n'/'N'/'F' 아님)
    assert isinstance(exponent, int)
    assert -exponent == 12  # 공유 헬퍼 quantize scale 고정 12
    assert bar.close == Decimal("129.04")  # raw 원본 그대로


def test_adj_factor_falls_back_when_adjusted_missing(caplog: pytest.LogCaptureFixture) -> None:
    """adjusted_close 결측 → adj_factor=1 + WARNING(조용한 왜곡 방지)."""
    row = dict(_ROW_NO_SPLIT)
    del row["adjusted_close"]
    src = _make_source(rows=[row])
    with caplog.at_level(logging.WARNING):
        bar = src.fetch_daily_bars("AAPL")[0]
    assert bar.adj_factor == Decimal("1")
    assert any("수정종가) 결측" in r.message for r in caplog.records)


def test_missing_ohlcv_row_is_dropped_not_filled(caplog: pytest.LogCaptureFixture) -> None:
    """OHLCV 결측 행은 추측 채움 없이 누락(WARNING). 정상 행만 반환."""
    bad = dict(_ROW_NO_SPLIT)
    del bad["high"]
    src = _make_source(rows=[bad, _ROW_SPLIT])
    with caplog.at_level(logging.WARNING):
        bars = src.fetch_daily_bars("AAPL")
    assert len(bars) == 1
    assert any("OHLCV 결측" in r.message for r in caplog.records)


def test_empty_response_returns_empty_list() -> None:
    """데이터 없는 ticker(빈 배열)는 빈 리스트 — 추측 채움 금지."""
    src = _make_source(rows=[])
    assert src.fetch_daily_bars("NODATA") == []


def test_symbol_format_defaults_to_us_suffix() -> None:
    """심볼이 점 없으면 .US 접미사(명세 거래소 코드 필수). from/to/period/order/fmt 쿼리 전달."""
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[_ROW_NO_SPLIT])

    src = _make_source(httpx.MockTransport(_handler))
    src.fetch_daily_bars("AAPL", start=date(2024, 1, 1), end=date(2024, 6, 30))
    assert "/eod/AAPL.US" in str(captured["url"])
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["from"] == "2024-01-01"
    assert params["to"] == "2024-06-30"
    assert params["period"] == "d"
    assert params["fmt"] == "json"


def test_symbol_format_keeps_explicit_exchange() -> None:
    """ticker 에 이미 .EX 가 있으면 그대로 사용(미국 외 거래소 명시 — 추측 보정 금지)."""
    captured: dict[str, str] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    src = _make_source(httpx.MockTransport(_handler))
    src.fetch_daily_bars("MCD.MX")
    assert "/eod/MCD.MX" in captured["url"]
    assert "MCD.MX.US" not in captured["url"]  # 이중 접미사 금지


def test_auth_uses_query_token_not_header() -> None:
    """⚠️ 인증은 ?api_token 쿼리 파라미터(Tiingo 의 Authorization 헤더와 다름, 명세)."""
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["token"] = request.url.params.get("api_token")
        captured["auth_header"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json=[])

    src = _make_source(httpx.MockTransport(_handler))
    src.fetch_daily_bars("AAPL")
    assert captured["token"] == _FAKE_KEY
    assert captured["auth_header"] == ""  # 헤더 인증 안 씀


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """키 미설정 시 EodhdAuthError, 메시지에 EODHD_API_KEY 안내(키 값은 없으니 당연 비노출)."""
    monkeypatch.delenv("EODHD_API_KEY", raising=False)
    src = _make_source(rows=[])
    with pytest.raises(EodhdAuthError) as exc:
        src.fetch_daily_bars("AAPL")
    assert "EODHD_API_KEY" in str(exc.value)


def test_api_token_never_appears_in_exceptions_or_repr() -> None:
    """⚠️ 토큰이 예외 메시지·repr 어디에도 노출되지 않는다(logging-rules BLOCKING)."""
    src = _make_source(rows=[], status=401)
    with pytest.raises(EodhdAuthError) as exc:
        src.fetch_daily_bars("AAPL")
    assert _FAKE_KEY not in str(exc.value)
    assert _FAKE_KEY not in repr(src)


def test_token_not_in_our_logs_even_though_in_url(caplog: pytest.LogCaptureFixture) -> None:
    """⚠️ 토큰이 쿼리 URL 에 실리지만(쿼리 인증), **우리 어댑터 로거**는 토큰/완성 URL 을 안 남긴다.

    ⚠️ 별개 리스크(이 테스트로 드러남): httpx 라이브러리 자체 INFO 로거(httpx._client)는 토큰이 실린
    완성 URL 을 로깅한다 — 라이브러리 동작이라 어댑터 내부에서 끌 수 없고, 진입점에서 httpx 로거
    레벨을 WARNING 이상으로 올려 막아야 한다(logging-rules: 핸들러·레벨은 진입점 책임). 그래서
    여기서는 **우리 모듈(stockpick) 로거 레코드**만 검사한다(httpx 레코드는 진입점 가드 대상).
    """

    def _handler(request: httpx.Request) -> httpx.Response:
        # 토큰은 실제 요청 쿼리엔 있어야 정상(쿼리 인증)
        assert request.url.params.get("api_token") == _FAKE_KEY
        return httpx.Response(200, json=[_ROW_NO_SPLIT])

    src = _make_source(httpx.MockTransport(_handler))
    with caplog.at_level(logging.DEBUG):
        src.fetch_daily_bars("AAPL")
    our_records = [r for r in caplog.records if r.name.startswith("stockpick")]
    assert our_records  # 우리 INFO 로그가 실제로 남았는지(빈 검사로 통과하는 위양성 방지)
    assert all(_FAKE_KEY not in r.getMessage() for r in our_records)


def test_rate_limit_429_classified(caplog: pytest.LogCaptureFixture) -> None:
    """429 → EodhdRateLimitError, Retry-After 파싱, WARNING 로그(토큰 비노출)."""
    src = _make_source(rows=[], status=429, headers={"Retry-After": "60"})
    with caplog.at_level(logging.WARNING), pytest.raises(EodhdRateLimitError) as exc:
        src.fetch_daily_bars("AAPL")
    assert exc.value.retry_after_seconds == 60.0
    assert _FAKE_KEY not in str(exc.value)
    assert any("rate limit" in r.message.lower() for r in caplog.records)


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_http_errors_classified(status: int) -> None:
    """4xx/5xx(429·401·403 제외) → EodhdResponseError, status_code 보존."""
    src = _make_source(rows=[], status=status)
    with pytest.raises(EodhdResponseError) as exc:
        src.fetch_daily_bars("AAPL")
    assert exc.value.status_code == status


@pytest.mark.parametrize("status", [401, 403])
def test_auth_errors_classified(status: int) -> None:
    """401/403 → EodhdAuthError(토큰 비노출)."""
    src = _make_source(rows=[], status=status)
    with pytest.raises(EodhdAuthError) as exc:
        src.fetch_daily_bars("AAPL")
    assert _FAKE_KEY not in str(exc.value)


def test_non_array_response_raises() -> None:
    """배열이 아닌 응답(예: 에러 객체)은 EodhdResponseError(조용한 무시 금지)."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "Symbol not found"})

    src = _make_source(httpx.MockTransport(_handler))
    with pytest.raises(EodhdResponseError):
        src.fetch_daily_bars("AAPL")


# ----- iter_universe (생존편향: 활성+폐지 병합) -----

_ACTIVE_SYMBOL: dict[str, object] = {
    "Code": "AAPL",
    "Name": "Apple Inc",
    "Country": "USA",
    "Exchange": "NASDAQ",
    "Currency": "USD",
    "Type": "Common Stock",
    "Isin": "US0378331005",
}
_DELISTED_SYMBOL: dict[str, object] = {
    "Code": "LEHMQ",
    "Name": "Lehman Brothers Holdings Inc",
    "Country": "USA",
    "Exchange": "PINK",
    "Currency": "USD",
    "Type": "Common Stock",
    "Isin": "",
}


def _universe_source(
    active: list[dict[str, object]], delisted: list[dict[str, object]]
) -> EodhdSource:
    """delisted 쿼리 파라미터로 활성/폐지 응답을 분기하는 MockTransport 소스."""

    def _handler(request: httpx.Request) -> httpx.Response:
        is_delisted = request.url.params.get("delisted") == "1"
        return httpx.Response(200, json=delisted if is_delisted else active)

    return _make_source(httpx.MockTransport(_handler))


def test_iter_universe_merges_active_and_delisted() -> None:
    """⚠️ 생존편향: include_delisted=True 면 활성 + delisted=1 두 호출을 병합(폐지 포함)."""
    src = _universe_source([_ACTIVE_SYMBOL], [_DELISTED_SYMBOL])
    stocks = src.iter_universe(include_delisted=True)
    tickers = {s.ticker for s in stocks}
    assert tickers == {"AAPL", "LEHMQ"}  # 폐지 종목 포함
    assert len(stocks) == 2


def test_iter_universe_cik_empty_and_exchange_mapped() -> None:
    """cik 는 EODHD 미제공 → 빈 문자열(EDGAR 매핑 후속). Exchange 코드는 enum 매핑."""
    src = _universe_source([_ACTIVE_SYMBOL], [])
    stocks = src.iter_universe(include_delisted=True)
    aapl = stocks[0]
    assert aapl.cik == ""  # 미제공 한계 — 조용한 추측 금지
    assert aapl.exchange == Exchange.NASDAQ
    assert aapl.delisted_at is None  # 폐지일 필드 명세 미제공


def test_iter_universe_unknown_exchange_falls_back_to_otc() -> None:
    """US 통합/미상 거래소 코드는 OTC 로 보수 분류(행을 버리지 않음 — 종목 보존)."""
    row = dict(_ACTIVE_SYMBOL)
    row["Exchange"] = "US"  # 통합 코드 — 세부 거래소 미상
    src = _universe_source([row], [])
    stocks = src.iter_universe(include_delisted=True)
    assert stocks[0].exchange == Exchange.OTC


def test_iter_universe_active_only_when_flag_false(caplog: pytest.LogCaptureFixture) -> None:
    """include_delisted=False 면 활성만(명시 요청), 생존편향 위험 WARNING."""
    src = _universe_source([_ACTIVE_SYMBOL], [_DELISTED_SYMBOL])
    with caplog.at_level(logging.WARNING):
        stocks = src.iter_universe(include_delisted=False)
    assert {s.ticker for s in stocks} == {"AAPL"}  # 폐지 미포함
    assert any("생존편향" in r.message for r in caplog.records)


def test_iter_universe_drops_rows_missing_code(caplog: pytest.LogCaptureFixture) -> None:
    """Code/Name 결측 행은 추측 채움 없이 누락 + WARNING(조용한 채움 금지)."""
    bad: dict[str, object] = {"Name": "No Code Corp", "Exchange": "NYSE"}  # Code 없음
    src = _universe_source([_ACTIVE_SYMBOL, bad], [])
    with caplog.at_level(logging.WARNING):
        stocks = src.iter_universe(include_delisted=True)
    assert {s.ticker for s in stocks} == {"AAPL"}
    assert any("결측" in r.message for r in caplog.records)
