"""POST /api/ingest — 라이브 EODHD 수집 트리거(동기).

흐름(플랜 §ingest): configure_logging()(httpx 토큰 누출 가드 — app startup 에서 1회지만 방어적으로
보장) → ingest_tickers(source, targets, start=None, end=None) → IngestSummary→IngestResult 매핑.

⚠️ 에러 매핑(키·토큰 비노출 BLOCKING): 어댑터/하위가 던지는 예외의 원문 메시지를 client 에 그대로
흘리지 않고 **상수 문자열**로 대체한다(EODHD 토큰이 메시지에 실릴 여지 차단). 상세는 서버 로그에만.
- EodhdAuthError    → 502 (서버 EODHD_API_KEY 문제)
- EodhdRateLimitError → 429 (무료 20콜/일 한도)
- VerificationError → 500 (적재 무결성 게이트 실패 — 생존편향 소실 등)
- 종목별 fetch 실패는 ingest_tickers 가 results.error 로 집계(200, passed=false — 조용한 누락 금지)

데모 유니버스: ingest._DEMO_UNIVERSE 는 모듈 private 라 import 불가 → api 가 동일 9종목을 복제 보유
(최소 변경 — data 모듈에 public 상수 승격을 피함. 보고에 명시).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ...data import configure_logging
from ...data.eodhd import EodhdAuthError, EodhdRateLimitError
from ...data.ingest import IngestSummary, ingest_tickers
from ...data.source import DataSource
from ...data.storage import VerificationError, VerificationReport
from ...types import Exchange
from ..deps import get_base_dir, get_source
from ..models import (
    IngestRequest,
    IngestResult,
    ShortfallModel,
    TickerIngestResultModel,
    VerificationModel,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ingest._DEMO_UNIVERSE 복제(private — import 불가). 두 곳이 갈라지면 데모 산출이 달라지므로
# data 모듈 변경 시 함께 갱신해야 한다(보고에 명시 — 향후 public 승격 검토).
_DEMO_UNIVERSE: tuple[tuple[str, Exchange], ...] = (
    ("AAPL", Exchange.NASDAQ),
    ("MSFT", Exchange.NASDAQ),
    ("NVDA", Exchange.NASDAQ),
    ("GOOGL", Exchange.NASDAQ),
    ("AMZN", Exchange.NASDAQ),
    ("META", Exchange.NASDAQ),
    ("JPM", Exchange.NYSE),
    ("JNJ", Exchange.NYSE),
    ("XOM", Exchange.NYSE),
)

_DETAIL_AUTH = "EODHD 인증 실패 — 서버 EODHD_API_KEY 확인"
_DETAIL_RATE = "EODHD rate limit 초과(무료 20콜/일) — 한도 리셋 후 재시도"
_DETAIL_VERIFY = "적재 무결성 게이트 실패 — 서버 로그 확인"


def _to_verification(report: VerificationReport | None) -> VerificationModel | None:
    if report is None:
        return None
    return VerificationModel(
        row_count=report.row_count,
        ticker_count=report.ticker_count,
        min_date=report.min_date,
        max_date=report.max_date,
        duplicate_count=report.duplicate_count,
        nonpositive_adj_factor_count=report.nonpositive_adj_factor_count,
        nonpositive_price_count=report.nonpositive_price_count,
        ohlc_violation_count=report.ohlc_violation_count,
        expected_checked=report.expected_checked,
        missing_tickers=list(report.missing_tickers),
        shortfall_tickers=[
            ShortfallModel(ticker=t, expected=e, actual=a) for (t, e, a) in report.shortfall_tickers
        ],
        orphan_tickers=list(report.orphan_tickers),
        passed=report.passed,
    )


def _to_result(summary: IngestSummary) -> IngestResult:
    return IngestResult(
        passed=summary.passed,
        total_rows=summary.total_rows,
        ingested_ticker_count=summary.ingested_ticker_count,
        empty_tickers=list(summary.empty_tickers),
        failed_tickers=list(summary.failed_tickers),
        results=[
            TickerIngestResultModel(
                ticker=r.ticker,
                exchange=r.exchange,
                bar_count=r.bar_count,
                min_date=r.min_date,
                max_date=r.max_date,
                error=r.error,
            )
            for r in summary.results
        ],
        verification=_to_verification(summary.report),
    )


@router.post("/ingest", response_model=IngestResult)
def ingest(
    body: IngestRequest | None = None,
    base_dir: Path = Depends(get_base_dir),
    source: DataSource = Depends(get_source),
) -> IngestResult:
    # httpx 토큰 누출 가드(EODHD ?api_token= 쿼리 인증). app startup 에서 이미 1회지만 방어적 보장.
    configure_logging()

    if body is not None and body.tickers is not None:
        targets = [(t.ticker, t.exchange) for t in body.tickers]
    else:
        targets = list(_DEMO_UNIVERSE)

    logger.info("ingest 요청: targets=%d종목, source=%s", len(targets), source.name)

    try:
        summary = ingest_tickers(source, targets, base_dir=base_dir, start=None, end=None)
    except EodhdAuthError:
        # 원문 메시지(토큰 실릴 여지) 비노출 — 상수 detail. 상세는 서버 로그(exception).
        logger.exception("ingest 인증 실패(EodhdAuthError) — 502")
        raise HTTPException(status_code=502, detail=_DETAIL_AUTH) from None
    except EodhdRateLimitError:
        logger.exception("ingest rate limit 초과(EodhdRateLimitError) — 429")
        raise HTTPException(status_code=429, detail=_DETAIL_RATE) from None
    except VerificationError:
        logger.exception("ingest 무결성 게이트 실패(VerificationError) — 500")
        raise HTTPException(status_code=500, detail=_DETAIL_VERIFY) from None

    return _to_result(summary)
