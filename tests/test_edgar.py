"""SEC EDGAR 어댑터(company_tickers + companyfacts) — 라이브 0(httpx.MockTransport).

검증: (ticker→cik) 10자리 zero-pad·대문자·형식불량 누락·신원/403→IdentityError·5xx→ResponseError·
User-Agent 전송·store/load 라운드트립. (companyfacts) 슬라이스 concept 추출·PIT(disclosed_at=filed)·
연/분기 혼재·concept 결측 빈리스트·형식불량 fact 누락·빈 cik/identity·403/500·CIK URL
·재무 store/load. 명세 실측 샘플 = docs/apis/sec-edgar/companyfacts.json(AAPL 라이브).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from stockpick.data.edgar import (
    EdgarError,
    EdgarIdentityError,
    EdgarResponseError,
    fetch_company_tickers,
    fetch_companyfacts,
    financials_path,
    load_financials,
    load_ticker_cik,
    store_financials,
    store_path,
    store_ticker_cik,
)
from stockpick.types import FinancialFact

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


# ---- companyfacts (#재무-1) ----

# docs/apis/sec-edgar/companyfacts.json 실측 구조(AAPL companyconcept 라이브 캡처 기반).
_FACTS_SAMPLE: dict[str, object] = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "StockholdersEquity": {
                "label": "Stockholders Equity",
                "units": {
                    "USD": [
                        {
                            "end": "2023-09-30",
                            "val": 62146000000,
                            "accn": "a1",
                            "fy": 2023,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2023-11-03",
                        },
                        {
                            "end": "2024-09-28",
                            "val": 56950000000,
                            "accn": "a2",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                        },
                    ]
                },
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "start": "2023-10-01",
                            "end": "2024-09-28",
                            "val": 93736000000,
                            "accn": "a2",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                        },
                        {
                            "start": "2024-03-31",
                            "end": "2024-06-29",
                            "val": 21448000000,
                            "accn": "a3",
                            "fy": 2024,
                            "fp": "Q3",
                            "form": "10-Q",
                            "filed": "2024-08-02",
                        },
                    ]
                },
            },
        },
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {
                    "shares": [
                        {
                            "end": "2024-10-18",
                            "val": 15115823000,
                            "accn": "a2",
                            "fy": 2024,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2024-11-01",
                            "frame": "CY2024Q3I",
                        },
                    ]
                },
            }
        },
    },
}


def test_fetch_companyfacts_extracts_slice_concepts() -> None:
    facts = fetch_companyfacts("0000320193", _IDENTITY, client=_json_client(_FACTS_SAMPLE))
    assert len(facts) == 5  # equity 2 + netincome 2(연·분기) + shares 1
    by_key = {(f.concept, f.fiscal_period): f for f in facts}
    eq = by_key[("StockholdersEquity", "2024-FY")]
    assert eq.cik == "0000320193"
    assert eq.value == Decimal("56950000000")
    assert eq.period_end == date(2024, 9, 28)  # end(회계기간말)
    assert eq.disclosed_at == date(2024, 11, 1)  # filed(PIT) — end 아님
    ni_q = by_key[("NetIncomeLoss", "2024-Q3")]  # 분기도 보존(연/분기 혼재)
    assert ni_q.value == Decimal("21448000000")
    shares = by_key[("EntityCommonStockSharesOutstanding", "2024-FY")]
    assert shares.value == Decimal("15115823000")  # dei taxonomy·units shares


def test_fetch_companyfacts_value_is_decimal() -> None:
    facts = fetch_companyfacts("0000320193", _IDENTITY, client=_json_client(_FACTS_SAMPLE))
    assert all(isinstance(f.value, Decimal) for f in facts)  # float 금지(정밀)


def test_fetch_companyfacts_missing_concepts_returns_empty() -> None:
    # 회사가 슬라이스 concept 미보유(IFRS·금융사 등) → 빈 리스트(에러 아님·결측 정상).
    payload = {"cik": 1, "entityName": "X", "facts": {"us-gaap": {}}}
    assert fetch_companyfacts("0000000001", _IDENTITY, client=_json_client(payload)) == []


def test_fetch_companyfacts_drops_malformed_facts() -> None:
    payload = {
        "cik": 1,
        "entityName": "X",
        "facts": {
            "us-gaap": {
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {
                                "end": "2024-09-28",
                                "val": 100,
                                "fy": 2024,
                                "fp": "FY",
                                "filed": "2024-11-01",
                            },
                            {
                                "end": "2024-09-28",
                                "val": "x",
                                "fy": 2024,
                                "fp": "FY",
                                "filed": "2024-11-01",
                            },  # val 비숫자
                            {
                                "end": "bad",
                                "val": 5,
                                "fy": 2024,
                                "fp": "FY",
                                "filed": "2024-11-01",
                            },  # end 불량
                            {"val": 5, "fy": 2024, "fp": "FY", "filed": "2024-11-01"},  # end 없음
                            "not-a-dict",
                        ]
                    }
                }
            }
        },
    }
    facts = fetch_companyfacts("0000000001", _IDENTITY, client=_json_client(payload))
    assert len(facts) == 1  # 정상 1건만, 나머지 추측 채움 없이 누락
    assert facts[0].value == Decimal("100")


def test_fetch_companyfacts_empty_identity_raises() -> None:
    with pytest.raises(EdgarIdentityError, match="EDGAR_IDENTITY"):
        fetch_companyfacts("0000320193", "", client=_json_client(_FACTS_SAMPLE))


def test_fetch_companyfacts_empty_cik_raises() -> None:
    with pytest.raises(EdgarResponseError, match="cik"):
        fetch_companyfacts("", _IDENTITY, client=_json_client(_FACTS_SAMPLE))


def test_fetch_companyfacts_missing_facts_key_raises() -> None:
    with pytest.raises(EdgarResponseError, match="facts"):
        fetch_companyfacts("0000320193", _IDENTITY, client=_json_client({"cik": 1}))


def test_fetch_companyfacts_403_raises_identity_error() -> None:
    with pytest.raises(EdgarIdentityError, match="403"):
        fetch_companyfacts("0000320193", _IDENTITY, client=_json_client({}, status=403))


def test_fetch_companyfacts_500_raises_response_error() -> None:
    with pytest.raises(EdgarResponseError):
        fetch_companyfacts("0000320193", _IDENTITY, client=_json_client({}, status=500))


def test_fetch_companyfacts_uses_cik_url_and_identity() -> None:
    captured: dict[str, str | None] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["ua"] = req.headers.get("user-agent")
        return httpx.Response(200, json=_FACTS_SAMPLE)

    fetch_companyfacts("0000320193", _IDENTITY, client=_client(httpx.MockTransport(handler)))
    assert captured["url"] == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    assert captured["ua"] == _IDENTITY


def test_financials_store_load_roundtrip(tmp_path: Path) -> None:
    facts = [
        FinancialFact(
            "0000320193",
            "StockholdersEquity",
            "2024-FY",
            date(2024, 9, 28),
            date(2024, 11, 1),
            Decimal("56950000000"),
        ),
        FinancialFact(
            "0000320193",
            "NetIncomeLoss",
            "2024-FY",
            date(2024, 9, 28),
            date(2024, 11, 1),
            Decimal("93736000000"),
        ),
    ]
    path = store_financials(facts, tmp_path)
    assert path == financials_path(tmp_path)
    assert path == tmp_path / "edgar" / "financials.json"
    assert load_financials(tmp_path) == facts  # Decimal·date 라운드트립 보존


def test_load_financials_missing_returns_empty(tmp_path: Path) -> None:
    assert load_financials(tmp_path) == []  # 미적재 → 빈 리스트(에러 아님)


def test_load_financials_malformed_raises(tmp_path: Path) -> None:
    path = financials_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(EdgarError, match="형식"):
        load_financials(tmp_path)
