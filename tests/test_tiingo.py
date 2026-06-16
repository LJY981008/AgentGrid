"""TiingoSource 어댑터 모킹 단위 테스트 — 라이브 호출 0(httpx.MockTransport).

응답 픽스처는 `docs/apis/tiingo/end-of-day.json` 의 response_fields 형태 그대로
(raw OHLCV + adjOpen/High/Low/Close + adjVolume + divCash + splitFactor). 검증 항목:
adj_factor=adjClose/close 산출 정확, raw 가격 Decimal 보존, 분할 케이스(adjClose≠close → factor≠1),
divCash 매핑(원본 불변 — DailyBar 엔 divCash 보관 안 함), 키 미설정 시 명확 에러, 키 비노출,
429/4xx 분류, 결측 행 누락(추측 채움 금지), iter_universe NotImplementedError(생존편향 명시).
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

import httpx
import pytest

from stockpick.data.source import DataSource
from stockpick.data.tiingo import (
    TiingoAuthError,
    TiingoRateLimitError,
    TiingoResponseError,
    TiingoSource,
)

_FAKE_KEY = "test-token-DO-NOT-LOG"

# end-of-day.json response_fields 형태 — AAPL 2024-06-03 부근(분할 없음: adjClose==close → factor 1)
_ROW_NO_SPLIT: dict[str, object] = {
    "date": "2024-06-03T00:00:00.000Z",
    "open": 192.9,
    "high": 194.99,
    "low": 192.52,
    "close": 194.03,
    "volume": 50080539,
    "adjOpen": 192.9,
    "adjHigh": 194.99,
    "adjLow": 192.52,
    "adjClose": 194.03,
    "adjVolume": 50080539,
    "divCash": 0.0,
    "splitFactor": 1.0,
}
# 분할/배당 조정 케이스: adjClose < close → factor < 1
_ROW_SPLIT: dict[str, object] = {
    "date": "2020-08-31T00:00:00.000Z",
    "open": 127.58,
    "high": 131.0,
    "low": 126.0,
    "close": 129.04,
    "volume": 225702700,
    "adjOpen": 126.0,
    "adjHigh": 129.4,
    "adjLow": 124.46,
    "adjClose": 127.46,
    "adjVolume": 225702700,
    "divCash": 0.0,
    "splitFactor": 4.0,
}


def _make_source(
    handler: httpx.MockTransport | None = None,
    *,
    rows: list[dict[str, object]] | None = None,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> TiingoSource:
    """MockTransport 를 단 TiingoSource — 라이브 호출 0. rows 지정 시 그 JSON 을 200 으로 반환."""
    if handler is None:

        def _default(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json=rows if rows is not None else [], headers=headers)

        handler = httpx.MockTransport(_default)
    client = httpx.Client(transport=handler)
    return TiingoSource(client=client)


@pytest.fixture(autouse=True)
def _set_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """대부분 테스트는 키가 설정된 상태 가정. 키 미설정 테스트는 개별 delenv."""
    monkeypatch.setenv("TIINGO_API_KEY", _FAKE_KEY)


def test_implements_datasource_protocol() -> None:
    """구조적으로 DataSource Protocol 을 만족(runtime_checkable isinstance)."""
    src = _make_source()
    assert isinstance(src, DataSource)
    assert src.name == "tiingo"


def test_fetch_daily_bars_maps_raw_ohlcv_decimal() -> None:
    """raw OHLCV 가 Decimal 로 보존되고 trade_date 가 타임스탬프 앞 10자에서 파싱된다."""
    src = _make_source(rows=[_ROW_NO_SPLIT])
    bars = src.fetch_daily_bars("AAPL")
    assert len(bars) == 1
    bar = bars[0]
    assert bar.ticker == "AAPL"
    assert bar.trade_date == date(2024, 6, 3)
    assert bar.open == Decimal("192.9")
    assert bar.close == Decimal("194.03")
    assert isinstance(bar.close, Decimal)
    assert bar.volume == 50080539
    assert bar.value is None  # Tiingo EOD 에 거래대금 필드 없음 — 추측 산출 안 함


def test_adj_factor_one_when_adjclose_equals_close() -> None:
    """무분할·무배당 구간: adjClose==close → adj_factor==1."""
    src = _make_source(rows=[_ROW_NO_SPLIT])
    bar = src.fetch_daily_bars("AAPL")[0]
    assert bar.adj_factor == Decimal("1")


def test_adj_factor_computed_from_adjclose_over_close_on_split() -> None:
    """분할 케이스: adj_factor = quantize(adjClose/close, 12자리), 1 아님. raw close 는 불변."""
    src = _make_source(rows=[_ROW_SPLIT])
    bar = src.fetch_daily_bars("AAPL")[0]
    # TASK-C: 공유 헬퍼가 소수 12자리로 quantize(나눗셈 무한소수 꼬리 제거)
    expected = (Decimal("127.46") / Decimal("129.04")).quantize(
        Decimal("1E-12"), rounding=ROUND_HALF_EVEN
    )
    assert bar.adj_factor == expected
    assert bar.adj_factor != Decimal("1")
    exponent = bar.adj_factor.as_tuple().exponent  # 유한 Decimal → int(특수값 'n'/'N'/'F' 아님)
    assert isinstance(exponent, int)
    assert -exponent == 12  # scale 고정 12
    assert bar.close == Decimal("129.04")  # raw 원본 그대로


def test_adj_factor_falls_back_to_one_when_adjclose_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """adjClose 결측 → adj_factor=1 + WARNING(조용한 왜곡 방지)."""
    row = dict(_ROW_NO_SPLIT)
    del row["adjClose"]
    src = _make_source(rows=[row])
    with caplog.at_level(logging.WARNING):
        bar = src.fetch_daily_bars("AAPL")[0]
    assert bar.adj_factor == Decimal("1")
    assert any("수정종가) 결측" in r.message for r in caplog.records)


def test_adj_factor_falls_back_when_close_zero(caplog: pytest.LogCaptureFixture) -> None:
    """close=0 경계: 0 나눗셈 방어 → adj_factor=1 + WARNING."""
    row = dict(_ROW_NO_SPLIT)
    row["close"] = 0
    src = _make_source(rows=[row])
    with caplog.at_level(logging.WARNING):
        bar = src.fetch_daily_bars("AAPL")[0]
    assert bar.adj_factor == Decimal("1")
    assert any("raw close<=0" in r.message for r in caplog.records)


def test_missing_ohlcv_row_is_dropped_not_filled(caplog: pytest.LogCaptureFixture) -> None:
    """OHLCV 결측 행은 추측 채움 없이 누락(WARNING). 정상 행만 반환."""
    bad = dict(_ROW_NO_SPLIT)
    del bad["high"]
    src = _make_source(rows=[bad, _ROW_SPLIT])
    with caplog.at_level(logging.WARNING):
        bars = src.fetch_daily_bars("AAPL")
    assert len(bars) == 1  # 결측 행 누락, 정상 1행만
    assert any("OHLCV 결측" in r.message for r in caplog.records)


def test_empty_response_returns_empty_list() -> None:
    """데이터 없는 ticker(빈 배열)는 빈 리스트 — 추측 채움 금지."""
    src = _make_source(rows=[])
    assert src.fetch_daily_bars("NODATA") == []


def test_start_end_passed_as_iso_query_params() -> None:
    """start/end 가 ISO startDate/endDate 쿼리로, format=json 으로 전달되는지(명세 파라미터)."""
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[_ROW_NO_SPLIT])

    src = _make_source(httpx.MockTransport(_handler))
    src.fetch_daily_bars("AAPL", start=date(2024, 1, 1), end=date(2024, 6, 30))
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["startDate"] == "2024-01-01"
    assert params["endDate"] == "2024-06-30"
    assert params["format"] == "json"
    assert "/tiingo/daily/AAPL/prices" in str(captured["url"])


def test_auth_header_uses_token_prefix_not_bearer() -> None:
    """인증 헤더가 'Token <KEY>' (Bearer 아님, general-connecting 명세)."""
    captured: dict[str, str] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json=[])

    src = _make_source(httpx.MockTransport(_handler))
    src.fetch_daily_bars("AAPL")
    assert captured["auth"] == f"Token {_FAKE_KEY}"
    assert not captured["auth"].startswith("Bearer")


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """키 미설정 시 TiingoAuthError, 메시지에 키 값 비노출(키가 없으니 당연하나 명시 검증)."""
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    src = _make_source(rows=[])
    with pytest.raises(TiingoAuthError) as exc:
        src.fetch_daily_bars("AAPL")
    assert "TIINGO_API_KEY" in str(exc.value)


def test_api_key_never_appears_in_exceptions_or_repr() -> None:
    """⚠️ 키가 예외 메시지·repr 어디에도 노출되지 않는다(logging-rules BLOCKING)."""
    # 401 케이스에서 예외 메시지에 키 비노출
    src = _make_source(rows=[], status=401)
    with pytest.raises(TiingoAuthError) as exc:
        src.fetch_daily_bars("AAPL")
    assert _FAKE_KEY not in str(exc.value)
    # repr 에도 키 비노출
    assert _FAKE_KEY not in repr(src)


def test_key_not_in_url_or_query(caplog: pytest.LogCaptureFixture) -> None:
    """키가 URL/쿼리에 실리지 않고(헤더 인증만) 로그에도 안 나온다."""
    captured: dict[str, str] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[_ROW_NO_SPLIT])

    src = _make_source(httpx.MockTransport(_handler))
    with caplog.at_level(logging.DEBUG):
        src.fetch_daily_bars("AAPL")
    assert _FAKE_KEY not in captured["url"]
    assert all(_FAKE_KEY not in r.getMessage() for r in caplog.records)


def test_rate_limit_429_classified(caplog: pytest.LogCaptureFixture) -> None:
    """429 → TiingoRateLimitError, Retry-After 파싱, WARNING 로그(키 비노출)."""
    src = _make_source(rows=[], status=429, headers={"Retry-After": "120"})
    with caplog.at_level(logging.WARNING), pytest.raises(TiingoRateLimitError) as exc:
        src.fetch_daily_bars("AAPL")
    assert exc.value.retry_after_seconds == 120.0
    assert _FAKE_KEY not in str(exc.value)
    assert any("rate limit" in r.message.lower() for r in caplog.records)


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_http_errors_classified(status: int) -> None:
    """4xx/5xx(429·401·403 제외) → TiingoResponseError, status_code 보존."""
    src = _make_source(rows=[], status=status)
    with pytest.raises(TiingoResponseError) as exc:
        src.fetch_daily_bars("AAPL")
    assert exc.value.status_code == status


def test_non_array_response_raises() -> None:
    """배열이 아닌 응답(예: 에러 객체)은 TiingoResponseError(조용한 무시 금지)."""

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"detail": "Error: not an array"})

    src = _make_source(httpx.MockTransport(_handler))
    with pytest.raises(TiingoResponseError):
        src.fetch_daily_bars("AAPL")


def test_iter_universe_raises_not_implemented_with_survivorship_reason() -> None:
    """⚠️ 생존편향 BLOCKING: 전체 유니버스 미지원 → 빈 리스트 아닌 NotImplementedError + 사유."""
    src = _make_source()
    with pytest.raises(NotImplementedError) as exc:
        src.iter_universe(include_delisted=True)
    msg = str(exc.value)
    assert "유니버스" in msg
    assert "생존편향" in msg
    assert "Sharadar" in msg  # 보강 경로 명시


def test_search_assets_returns_raw_with_isactive() -> None:
    """search_assets 는 raw dict 리스트 반환 — isActive(폐지 식별) 보존."""
    search_row = {
        "ticker": "AAPL",
        "name": "Apple Inc",
        "assetType": "Stock",
        "isActive": True,
        "permaTicker": "",
        "openFIGI": "",
    }
    src = _make_source(rows=[search_row])
    results = src.search_assets("apple")
    assert results[0]["ticker"] == "AAPL"
    assert results[0]["isActive"] is True
