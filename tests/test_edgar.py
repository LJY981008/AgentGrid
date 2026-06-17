"""SEC EDGAR company_tickers 어댑터 — 라이브 0(httpx.MockTransport). 명세 실측 샘플 사용.

검증: ticker→cik 10자리 zero-pad·대문자 정규화·형식불량 누락·신원 누락/403→IdentityError·5xx→
ResponseError·User-Agent 헤더 전송·store/load 라운드트립·파일없음 빈맵·형식오류 명시 실패.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from stockpick.data.edgar import (
    EdgarIdentityError,
    EdgarResponseError,
    fetch_company_tickers,
    load_ticker_cik,
    store_path,
    store_ticker_cik,
)

# docs/apis/sec-edgar/company-tickers.json 실측 샘플 구조(인덱스 키 비안정·cik_str int)
_SAMPLE: dict[str, object] = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "2": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
}
_IDENTITY = "Test User test@example.com"


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def _json_client(payload: object, *, status: int = 200) -> httpx.Client:
    return _client(httpx.MockTransport(lambda _req: httpx.Response(status, json=payload)))


def test_fetch_maps_ticker_to_zeropad_cik() -> None:
    mapping = fetch_company_tickers(_IDENTITY, client=_json_client(_SAMPLE))
    assert mapping == {
        "NVDA": "0001045810",
        "AAPL": "0000320193",
        "GOOGL": "0001652044",
    }


def test_fetch_uppercases_ticker() -> None:
    payload = {"0": {"cik_str": 111, "ticker": "tsla", "title": "Tesla"}}
    mapping = fetch_company_tickers(_IDENTITY, client=_json_client(payload))
    assert mapping == {"TSLA": "0000000111"}


def test_fetch_drops_malformed_entries() -> None:
    payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"},
        "1": {"ticker": "NOCIK"},  # cik_str 없음 → 누락
        "2": {"cik_str": 5, "title": "no ticker"},  # ticker 없음 → 누락
        "3": "not-a-dict",  # 형식 불량 → 누락
    }
    assert fetch_company_tickers(_IDENTITY, client=_json_client(payload)) == {"AAPL": "0000320193"}


def test_fetch_empty_identity_raises() -> None:
    with pytest.raises(EdgarIdentityError, match="EDGAR_IDENTITY"):
        fetch_company_tickers("", client=_json_client(_SAMPLE))
    with pytest.raises(EdgarIdentityError):
        fetch_company_tickers("   ", client=_json_client(_SAMPLE))


def test_fetch_403_raises_identity_error() -> None:
    # SEC 403 = User-Agent 신원 거부(또는 rate limit) → IdentityError.
    with pytest.raises(EdgarIdentityError, match="403"):
        fetch_company_tickers(_IDENTITY, client=_json_client({}, status=403))


def test_fetch_500_raises_response_error() -> None:
    with pytest.raises(EdgarResponseError):
        fetch_company_tickers(_IDENTITY, client=_json_client({}, status=500))


def test_fetch_sends_user_agent_identity() -> None:
    captured: dict[str, str | None] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["ua"] = req.headers.get("user-agent")
        return httpx.Response(200, json=_SAMPLE)

    fetch_company_tickers(_IDENTITY, client=_client(httpx.MockTransport(handler)))
    assert captured["ua"] == _IDENTITY  # SEC 필수 신원 헤더 전송 확인


def test_store_load_roundtrip(tmp_path: Path) -> None:
    mapping = {"AAPL": "0000320193", "NVDA": "0001045810"}
    path = store_ticker_cik(mapping, tmp_path)
    assert path == store_path(tmp_path)
    assert path == tmp_path / "edgar" / "ticker_cik.json"
    assert load_ticker_cik(tmp_path) == mapping


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert load_ticker_cik(tmp_path) == {}  # 미적재 → 빈 맵(cik="" 폴백·에러 아님)


def test_load_malformed_raises(tmp_path: Path) -> None:
    path = store_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('["not", "a", "dict"]', encoding="utf-8")
    with pytest.raises(Exception, match="형식"):
        load_ticker_cik(tmp_path)
