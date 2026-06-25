"""API 층 테스트 — TestClient + dependency_overrides(라이브 호출 0).

전략(플랜 §테스트): `app.dependency_overrides` 로 base_dir·learning_dir·source 를 교체한다(Spring
@TestConfiguration 처럼 협력자만 바꿔치기). dataset·ranking 은 **합성 Parquet**(write_daily_bars 로
tmp 적재)을 주입해 실제 DuckDB 스캔 경로를 타되 데이터는 결정적. ingest 는 **FakeSource**(DataSource
Protocol 구현 — 네트워크 0)로 에러 매핑·키 비노출을 검증한다.

⚠️ 라이브 EODHD 호출은 한 건도 없다(픽스처·페이크만). 금융 BLOCKING 단언: ranking 은
meta.validated is False + warning 존재를 못박는다(§4.1 — 미검증 룰 경고 상시).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stockpick.api import create_app
from stockpick.api.deps import get_base_dir, get_learning_dir, get_source
from stockpick.backtest.s6_gate import compute_rule_signature, ranking_rule_signature
from stockpick.data.edgar import store_financials, store_ticker_cik
from stockpick.data.eodhd import EodhdAuthError, EodhdRateLimitError
from stockpick.data.storage import write_daily_bars
from stockpick.types import DailyBar, Exchange, FinancialFact, Stock

_DUMMY_KEY = "DUMMY-SECRET-EODHD-KEY-9f3a"  # 키 비노출 단언용 — 응답에 이 값이 절대 안 나와야 함


def _bar(
    ticker: str, d: date, *, close: str, adj_factor: str = "1", volume: int = 1000
) -> DailyBar:
    # OHLC 정합(high>=, low<=) — close ±5 범위, low 는 0 미만 클램프(penny 안전).
    c = Decimal(close)
    return DailyBar(
        ticker=ticker,
        trade_date=d,
        open=c,
        high=c + Decimal("5"),
        low=max(Decimal("0.01"), c - Decimal("5")),
        close=c,
        volume=volume,
        value=None,
        adj_factor=Decimal(adj_factor),
    )


def _write_synthetic(base_dir: Path) -> None:
    """결정적 합성 Parquet — 2종목·상승 추세(모멘텀 산출 가능하게 충분한 거래일)."""
    # NVDA: 강한 상승(모멘텀 1위 예상), AAPL: 완만한 상승. 60거래일.
    start = date(2025, 1, 1)
    nvda = [_bar("NVDA", start + timedelta(days=i), close=str(100 + i * 2)) for i in range(60)]
    aapl = [_bar("AAPL", start + timedelta(days=i), close=str(100 + i)) for i in range(60)]
    write_daily_bars(nvda, exchange=Exchange.NASDAQ, base_dir=base_dir, source="synthetic")
    write_daily_bars(aapl, exchange=Exchange.NASDAQ, base_dir=base_dir, source="synthetic")


# ---------------------------------------------------------------------------
# FakeSource — DataSource Protocol 구현(네트워크 0)
# ---------------------------------------------------------------------------


class FakeSource:
    """라이브 0 수집용 페이크. bars 를 그대로 돌려주거나, 지정 예외를 던진다(에러 매핑 테스트)."""

    def __init__(
        self,
        *,
        bars_by_ticker: dict[str, list[DailyBar]] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self._bars = bars_by_ticker or {}
        self._raise = raise_exc

    @property
    def name(self) -> str:
        return "fake"

    def iter_universe(self, *, include_delisted: bool = True) -> list[Stock]:
        return []

    def fetch_daily_bars(
        self,
        ticker: str,
        *,
        start: date | None = None,
        end: date | None = None,
    ) -> list[DailyBar]:
        if self._raise is not None:
            raise self._raise
        return self._bars.get(ticker, [])


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """합성 base_dir·learning_dir 주입 TestClient(라이브 0). source 는 케이스별 추가 override."""
    app = create_app()
    base_dir = tmp_path / "parquet"
    learning_dir = tmp_path / "learning"
    base_dir.mkdir(parents=True)
    learning_dir.mkdir(parents=True)
    app.dependency_overrides[get_base_dir] = lambda: base_dir
    app.dependency_overrides[get_learning_dir] = lambda: learning_dir
    with TestClient(app) as c:
        # tmp 경로·app 을 케이스에서 쓸 수 있게 client 에 부착(테스트 편의). client.app 은 starlette
        # 가 ASGIApp(Callable)로 타입팅해 dependency_overrides 가 없으므로, FastAPI app 을 별도
        # 속성(fastapi_app)으로 노출한다(케이스가 source override 를 걸 지점).
        c.base_dir = base_dir
        c.learning_dir = learning_dir
        c.fastapi_app = app
        yield c


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]  # 비어있지 않음("0.0.1" 또는 "unknown")


def test_metrics_endpoint(client: TestClient) -> None:
    """instrumentator /metrics — Prometheus 텍스트(HTTP 요청 지연 메트릭)·/api prefix 밖."""
    client.get("/api/health")  # 요청 1회 → 메트릭 발생
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "http_request" in r.text  # http_request_duration_seconds·http_requests_total 류


# ---------------------------------------------------------------------------
# dataset
# ---------------------------------------------------------------------------


def test_dataset_empty_tree(client: TestClient) -> None:
    r = client.get("/api/dataset")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker_count"] == 0
    assert body["total_rows"] == 0
    assert body["tickers"] == []
    assert body["sources"] == []
    assert body["min_date"] is None


def test_dataset_synthetic(client: TestClient) -> None:
    _write_synthetic(client.base_dir)
    r = client.get("/api/dataset")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker_count"] == 2
    assert body["total_rows"] == 120  # 2종목 × 60거래일
    assert body["sources"] == ["synthetic"]
    tickers = {t["ticker"]: t for t in body["tickers"]}
    assert tickers["NVDA"]["row_count"] == 60
    assert tickers["NVDA"]["exchange"] == "NASDAQ"
    assert tickers["NVDA"]["source"] == "synthetic"
    assert tickers["NVDA"]["min_date"] == "2025-01-01"


# ---------------------------------------------------------------------------
# ranking — §4.1 미검증 경고 단언
# ---------------------------------------------------------------------------


def test_ranking_synthetic_validated_false_and_warning(client: TestClient) -> None:
    _write_synthetic(client.base_dir)
    r = client.get("/api/ranking", params={"top_n": 5, "lookback_days": 20, "skip_recent_days": 0})
    assert r.status_code == 200
    body = r.json()
    # ⭐ BLOCKING: 미검증 경고 상시(§4.1)
    assert body["meta"]["validated"] is False
    assert body["meta"]["warning"]  # 경고 문자열 존재
    assert "§4.1" in body["meta"]["warning"]
    # 엔트리 비어있지 않고 형태 검증
    assert len(body["entries"]) >= 1
    entry = body["entries"][0]
    assert set(entry) == {"cik", "ticker", "exchange", "rank", "score", "rule_version", "factors"}
    assert entry["rule_version"] == "v0-momentum-20"
    assert "momentum" in entry["factors"]
    # 강한 상승(NVDA)이 1위
    assert body["entries"][0]["ticker"] == "NVDA"
    assert body["meta"]["as_of"] is not None
    assert body["meta"]["params"]["top_n"] == 5


def test_ranking_empty_tree_keeps_warning(client: TestClient) -> None:
    r = client.get("/api/ranking")
    assert r.status_code == 200
    body = r.json()
    assert body["entries"] == []
    assert body["meta"]["validated"] is False
    assert body["meta"]["warning"]
    assert body["meta"]["as_of"] is None


def _write_gate_result(base_dir: Path, *, signature: str, passed: bool) -> None:
    """flip 테스트용 s6_gate_result.json 직접 기록(verdict 는 passed+signature 만 읽음)."""
    (base_dir / "s6_gate_result.json").write_text(
        json.dumps({"passed": passed, "rule_signature": signature}), encoding="utf-8"
    )


def test_ranking_validated_true_when_gate_passed_and_signature_matches(client: TestClient) -> None:
    _write_synthetic(client.base_dir)
    # R4: display top_n 은 signature 무관(decile 부분집합) — lookback/skip/group 일치 시 flip.
    sig = ranking_rule_signature(lookback_days=20, skip_recent_days=0, group_by_exchange=True)
    _write_gate_result(client.base_dir, signature=sig, passed=True)
    r = client.get("/api/ranking", params={"top_n": 5, "lookback_days": 20, "skip_recent_days": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["validated"] is True  # 게이트 통과·signature 일치 → flip
    assert "검증" in body["meta"]["warning"]  # 미검증 경고 대신 검증 메시지


def test_ranking_validated_false_when_signature_mismatch(client: TestClient) -> None:
    # 게이트 통과 파일이 있어도 다른 룰(lookback 불일치) 요청이면 false(검증 범위=통과한 그 룰뿐).
    _write_synthetic(client.base_dir)
    sig = ranking_rule_signature(
        lookback_days=99, skip_recent_days=0, group_by_exchange=True
    )
    _write_gate_result(client.base_dir, signature=sig, passed=True)
    r = client.get("/api/ranking", params={"top_n": 5, "lookback_days": 20, "skip_recent_days": 0})
    assert r.status_code == 200
    assert r.json()["meta"]["validated"] is False


def test_ranking_excludes_illiquid_when_cache_present(client: TestClient) -> None:
    # ADR-010 (c) 사후 유동성 필터 — cache.duckdb 있으면 penny(close<$5)/비유동을 랭킹서 제외
    # (검증 decile 와 동일 유니버스). cache 부재면 Noop(기존 테스트 불변).
    from stockpick.data.duckdb_cache import build_cache

    base = client.base_dir
    start = date(2025, 1, 1)
    liq = [
        _bar("LIQ", start + timedelta(days=i), close=str(100 + i), volume=50000) for i in range(60)
    ]
    penny = [
        _bar("PENNY", start + timedelta(days=i), close="4", volume=50000) for i in range(60)
    ]
    write_daily_bars(liq, exchange=Exchange.NASDAQ, base_dir=base, source="synthetic")
    write_daily_bars(penny, exchange=Exchange.NASDAQ, base_dir=base, source="synthetic")
    build_cache(base)  # cache.duckdb(volume) — 사후 유동성 필터 활성
    r = client.get(
        "/api/ranking", params={"lookback_days": 20, "skip_recent_days": 0, "group": "all"}
    )
    assert r.status_code == 200
    tickers = [e["ticker"] for e in r.json()["entries"]]
    assert "LIQ" in tickers
    assert "PENNY" not in tickers  # close<$5 → 유동성 필터 제외


def test_backtest_validated_true_when_gate_passed_and_signature_matches(
    client: TestClient,
) -> None:
    _write_synthetic(client.base_dir)
    sig = compute_rule_signature(
        strategy_name="equal_weight_top_n",
        top_n=5,
        lookback_days=126,
        skip_recent_days=21,
        rebalance_freq="monthly",
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
    )
    _write_gate_result(client.base_dir, signature=sig, passed=True)
    r = client.get("/api/backtest")  # 기본 strategy=equal_weight·top_n=5·monthly
    assert r.status_code == 200
    assert r.json()["meta"]["validated"] is True


def test_backtest_validated_false_when_gate_failed(client: TestClient) -> None:
    # signature 일치해도 passed=false 면 false.
    _write_synthetic(client.base_dir)
    sig = compute_rule_signature(
        strategy_name="equal_weight_top_n",
        top_n=5,
        lookback_days=126,
        skip_recent_days=21,
        rebalance_freq="monthly",
        delisting_recovery_rate=Decimal("0"),
        group_by_exchange=False,
    )
    _write_gate_result(client.base_dir, signature=sig, passed=False)
    r = client.get("/api/backtest")
    assert r.status_code == 200
    assert r.json()["meta"]["validated"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"top_n": 0},
        {"lookback_days": 0},
        {"skip_recent_days": -1},
        {"group": "foo"},
    ],
)
def test_ranking_param_validation_422(client: TestClient, params: dict[str, object]) -> None:
    r = client.get("/api/ranking", params=params)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# ingest — FakeSource(라이브 0), 키 비노출, 에러 매핑
# ---------------------------------------------------------------------------


def test_ingest_demo_with_fake_source(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EODHD_API_KEY", _DUMMY_KEY)
    fake = FakeSource(
        bars_by_ticker={
            "AAPL": [
                _bar("AAPL", date(2025, 1, 1), close="100"),
                _bar("AAPL", date(2025, 1, 2), close="101"),
            ],
        }
    )
    client.fastapi_app.dependency_overrides[get_source] = lambda: fake
    # body 생략 → 데모 9종목. FakeSource 는 AAPL 만 bars 제공, 나머지는 빈 결과(데이터 부족).
    r = client.post("/api/ingest", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] == 2
    assert body["ingested_ticker_count"] == 1
    assert "AAPL" not in body["empty_tickers"]
    assert len(body["results"]) == 9  # 데모 9종목 전부 결과 기록(0행 포함 — 조용한 누락 금지)
    # 키 비노출: 응답 본문 어디에도 더미 키가 없어야 함
    assert _DUMMY_KEY not in r.text


def test_ingest_explicit_tickers(client: TestClient) -> None:
    fake = FakeSource(bars_by_ticker={"MSFT": [_bar("MSFT", date(2025, 1, 1), close="200")]})
    client.fastapi_app.dependency_overrides[get_source] = lambda: fake
    r = client.post(
        "/api/ingest",
        json={"tickers": [{"ticker": "MSFT", "exchange": "NASDAQ"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["ticker"] == "MSFT"
    assert body["total_rows"] == 1


def test_ingest_unknown_exchange_422(client: TestClient) -> None:
    fake = FakeSource()
    client.fastapi_app.dependency_overrides[get_source] = lambda: fake
    r = client.post(
        "/api/ingest",
        json={"tickers": [{"ticker": "MSFT", "exchange": "KOSPI"}]},
    )
    assert r.status_code == 422  # 알 수 없는 Exchange — pydantic 검증(추측 매핑 금지)


def test_ingest_auth_error_502_no_key_leak(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EODHD_API_KEY", _DUMMY_KEY)
    fake = FakeSource(raise_exc=EodhdAuthError(f"auth failed token={_DUMMY_KEY}"))
    client.fastapi_app.dependency_overrides[get_source] = lambda: fake
    r = client.post("/api/ingest", json={"tickers": [{"ticker": "AAPL", "exchange": "NASDAQ"}]})
    assert r.status_code == 502
    assert _DUMMY_KEY not in r.text  # 원문 예외(키 포함) 비노출 — 상수 detail 만
    assert "EODHD_API_KEY" in r.json()["detail"]  # 친화 메시지


def test_ingest_rate_limit_429_no_key_leak(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EODHD_API_KEY", _DUMMY_KEY)
    fake = FakeSource(raise_exc=EodhdRateLimitError(f"429 token={_DUMMY_KEY}"))
    client.fastapi_app.dependency_overrides[get_source] = lambda: fake
    r = client.post("/api/ingest", json={"tickers": [{"ticker": "AAPL", "exchange": "NASDAQ"}]})
    assert r.status_code == 429
    assert _DUMMY_KEY not in r.text
    assert "rate limit" in r.json()["detail"]


# ---------------------------------------------------------------------------
# learning — tree·content·path traversal
# ---------------------------------------------------------------------------


def _seed_learning(learning_dir: Path) -> None:
    (learning_dir / "00.caveats.md").write_text("# 주의\n생존편향·룩어헤드", encoding="utf-8")
    sub = learning_dir / "04.financial-statements"
    sub.mkdir()
    (sub / "01.balance-sheet.md").write_text("# 재무상태표\n![img](./x.png)", encoding="utf-8")
    (sub / "x.png").write_bytes(b"\x89PNG")  # 마크다운 아님 — content 로 못 읽어야 함


def test_learning_tree(client: TestClient) -> None:
    _seed_learning(client.learning_dir)
    r = client.get("/api/learning/tree")
    assert r.status_code == 200
    root = r.json()["root"]
    names = [n["name"] for n in root]
    assert "00.caveats.md" in names
    # 00.caveats 가 최상단(숫자 접두사 정렬)
    assert root[0]["name"] == "00.caveats.md"
    # 디렉토리 노드 + 자식
    dirs = [n for n in root if n["type"] == "dir"]
    assert any(d["name"] == "04.financial-statements" for d in dirs)
    fin = next(d for d in dirs if d["name"] == "04.financial-statements")
    assert any(c["name"] == "01.balance-sheet.md" for c in fin["children"])


def test_learning_content(client: TestClient) -> None:
    _seed_learning(client.learning_dir)
    r = client.get(
        "/api/learning/content",
        params={"path": "04.financial-statements/01.balance-sheet.md"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "재무상태표" in body["content"]
    assert body["dir"] == "04.financial-statements"
    assert body["path"] == "04.financial-statements/01.balance-sheet.md"


def test_learning_content_top_level_dir_empty(client: TestClient) -> None:
    _seed_learning(client.learning_dir)
    r = client.get("/api/learning/content", params={"path": "00.caveats.md"})
    assert r.status_code == 200
    assert r.json()["dir"] == ""  # 최상위 파일 → dir 빈 문자열


def test_learning_content_traversal_404(client: TestClient) -> None:
    _seed_learning(client.learning_dir)
    r = client.get("/api/learning/content", params={"path": "../../etc/passwd"})
    assert r.status_code == 404  # 경로 이탈 차단(존재 여부 비노출)


def test_learning_content_non_markdown_404(client: TestClient) -> None:
    _seed_learning(client.learning_dir)
    r = client.get("/api/learning/content", params={"path": "04.financial-statements/x.png"})
    assert r.status_code == 404  # 마크다운 아님 — 임의 파일 읽기 차단


def test_learning_content_missing_404(client: TestClient) -> None:
    _seed_learning(client.learning_dir)
    r = client.get("/api/learning/content", params={"path": "nope.md"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# backtest — §4.1 미검증 경고 단언 + 골격 shape
# ---------------------------------------------------------------------------


def test_backtest_synthetic_validated_false_and_warning(client: TestClient) -> None:
    _write_synthetic(client.base_dir)
    r = client.get("/api/backtest", params={"top_n": 2})
    assert r.status_code == 200
    body = r.json()
    # §4.1 BLOCKING: 골격은 항상 미검증.
    assert body["meta"]["validated"] is False
    assert body["meta"]["warning"]
    assert body["meta"]["data_caveats"]  # 골격 한계 고지 비어있지 않음
    assert len(body["equity_curve"]) >= 1  # 자산곡선 산출
    assert len(body["benchmark_curve"]) >= 1  # 등가중 벤치 곡선
    assert "EQUAL_WEIGHT_UNIVERSE" in body["benchmark_returns"]
    assert body["metrics"]["n_rebalances"] >= 1
    # 자산곡선 첫 점 = 초기자본 1.0 앵커.
    assert body["equity_curve"][0]["value"] == 1.0


def test_backtest_empty_tree_keeps_warning(client: TestClient) -> None:
    # 데이터 없음 → 200·빈 곡선·warning 유지(에러 아님, ranking 선례).
    r = client.get("/api/backtest")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["validated"] is False
    assert body["meta"]["warning"]
    assert body["equity_curve"] == []
    assert body["metrics"]["total_return"] == 0.0


def test_backtest_score_weight_strategy(client: TestClient) -> None:
    _write_synthetic(client.base_dir)
    r = client.get(
        "/api/backtest", params={"strategy": "score_weight", "rebalance_freq": "monthly"}
    )
    assert r.status_code == 200
    assert r.json()["meta"]["params"]["strategy"] == "score_weight"


def test_backtest_invalid_params_422(client: TestClient) -> None:
    assert client.get("/api/backtest", params={"top_n": 0}).status_code == 422  # ge=1 위반
    assert client.get("/api/backtest", params={"strategy": "bogus"}).status_code == 422  # Literal
    assert client.get("/api/backtest", params={"rebalance_freq": "weekly"}).status_code == 422


# ---------------------------------------------------------------------------
# EDGAR cik enrich (#2) — ranking 응답 cik 채움(저장본 있으면)·없으면 graceful
# ---------------------------------------------------------------------------


def test_ranking_cik_enriched_from_edgar_store(client: TestClient) -> None:
    _write_synthetic(client.base_dir)  # NVDA·AAPL
    store_ticker_cik({"NVDA": "0001045810", "AAPL": "0000320193"}, client.base_dir)
    r = client.get("/api/ranking", params={"top_n": 5, "lookback_days": 20, "skip_recent_days": 0})
    assert r.status_code == 200
    ciks = {e["ticker"]: e["cik"] for e in r.json()["entries"]}
    assert ciks["NVDA"] == "0001045810"
    assert ciks["AAPL"] == "0000320193"


def test_ranking_cik_empty_without_edgar_store(client: TestClient) -> None:
    _write_synthetic(client.base_dir)  # EDGAR 저장본 없음 → cik="" 폴백(graceful)
    r = client.get("/api/ranking", params={"top_n": 5, "lookback_days": 20, "skip_recent_days": 0})
    assert r.status_code == 200
    assert all(e["cik"] == "" for e in r.json()["entries"])


# ---------------------------------------------------------------------------
# 재무 팩터 enrich (#재무-1) — factors 에 roe/pb 추가(rank 불변·미해소 키 생략·룩어헤드)
# ---------------------------------------------------------------------------


def _store_nvda_financials(base_dir: Path, *, filed: tuple[int, int, int]) -> None:
    # NVDA cik=0001045810 의 슬라이스 재무(연간). period_end 2024-12-31.
    cik = "0001045810"
    facts = [
        FinancialFact(
            cik, "StockholdersEquity", "2024-FY", date(2024, 12, 31), date(*filed), Decimal("1000")
        ),
        FinancialFact(
            cik, "NetIncomeLoss", "2024-FY", date(2024, 12, 31), date(*filed), Decimal("200")
        ),
        FinancialFact(
            cik,
            "EntityCommonStockSharesOutstanding",
            "2024-FY",
            date(2024, 12, 31),
            date(*filed),
            Decimal("100"),
        ),
    ]
    store_financials(facts, base_dir)


def test_ranking_financial_factors_enriched(client: TestClient) -> None:
    _write_synthetic(client.base_dir)  # NVDA 마지막 close=218 @2025-03-01
    store_ticker_cik({"NVDA": "0001045810", "AAPL": "0000320193"}, client.base_dir)
    _store_nvda_financials(client.base_dir, filed=(2025, 1, 15))  # as_of(2025-03-01) 이전 공시
    r = client.get("/api/ranking", params={"top_n": 5, "lookback_days": 20, "skip_recent_days": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["entries"][0]["ticker"] == "NVDA"  # rank 불변(모멘텀만 — 재무 결합 안 함)
    entries = {e["ticker"]: e for e in body["entries"]}
    nvda = entries["NVDA"]
    assert nvda["factors"]["roe"] == pytest.approx(0.2)  # 200/1000
    assert nvda["factors"]["pb"] == pytest.approx(21.8)  # close 218 * shares 100 / equity 1000
    assert "momentum" in nvda["factors"]  # 기존 팩터 보존
    # AAPL: cik 해소되나 재무 미적재 → roe/pb 키 생략(미해소).
    aapl = entries["AAPL"]
    assert "roe" not in aapl["factors"]
    assert "pb" not in aapl["factors"]


def test_ranking_financial_factors_lookahead_excludes_future_filing(client: TestClient) -> None:
    _write_synthetic(client.base_dir)
    store_ticker_cik({"NVDA": "0001045810"}, client.base_dir)
    _store_nvda_financials(client.base_dir, filed=(2026, 2, 1))  # as_of 이후 공시 → 누설 차단
    r = client.get(
        "/api/ranking",
        params={"as_of": "2025-03-01", "top_n": 5, "lookback_days": 20, "skip_recent_days": 0},
    )
    assert r.status_code == 200
    nvda = next(e for e in r.json()["entries"] if e["ticker"] == "NVDA")
    assert "roe" not in nvda["factors"]  # 미래 공시 미사용(룩어헤드 BLOCKING)
    assert "pb" not in nvda["factors"]
