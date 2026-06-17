"""소스 무관 generic 적재기 — (ticker, exchange) 목록을 fetch→저장→누적검증(M2 데이터셋 생성).

`pilot.py`(Tiingo 5종목 분할 교차검증 전용)와 달리 이 모듈은 **어떤 DataSource 든**(Tiingo·
EODHD·향후 Sharadar) (ticker, exchange) 시퀀스를 받아 미니/대형 데이터셋을 만드는 재사용 도구다.
M2 룰엔진·백테스트가 스캔할 실데이터셋을 `data/parquet/` 에 영속화한다.

흐름(종목별): `source.fetch_daily_bars(ticker, start, end)` → `write_daily_bars`(그 종목의
exchange 파티션) → **누적 expected 로 `verify_parquet`**. 누적 검증은 TASK-B 소실탐지 가드를
재사용한다 — i번째 종목 적재가 같은 파티션의 이전 종목을 조용히 소실시키면 누적 expected 대조가
VerificationError 로 시끄럽게 실패한다(생존편향 누수 봉인).

⚠️ 실패 명확 보고(BLOCKING): 빈 결과(0행)·종목별 fetch 에러는 조용히 삼키지 않고 명확히 집계·
로그한다. 0행은 데이터 부족이지 소실이 아니므로(소실은 적재됐던 ticker 가 사라지는 것) expected
에 넣지 않는다 — actual 0 과 정합. fetch 에러는 종목별로 포착해 집계하되, **인증·rate limit 은
전 종목 공통 실패이므로 즉시 전파**한다(개별 종목 문제로 오인 금지).

모듈 경계(python-conventions): `data` 는 `rules`/`backtest`/상위를 import 하지 않는다. 도메인
계약(`..types`)·인터페이스(`.source`)·저장층(`.storage`)·진입점 로깅 가드(`.`)만 의존한다.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Final

from ..types import Exchange
from . import configure_logging
from .eodhd import EodhdAuthError, EodhdRateLimitError, EodhdResponseError, EodhdSource
from .storage import (
    TickerExpectation,
    VerificationReport,
    build_expected,
    verify_parquet,
    write_daily_bars,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .source import DataSource

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR: Final = Path("data/parquet")

# 데모 유니버스 — 섹터·거래소 분산(M2 룰/백테스트 다양성). EODHD 무료티어는 종목당 1콜(20/일)이라
# 9종목 = 9콜로 한도 내.
# ⭐ history 무관(無하드코딩) 설계: 데모는 start/end 없이(=None) 호출해 **소스가 제공하는 전체**를
#   받는다. 무료티어는 최신 1년(251 거래일)을, **유료 결제 후엔 같은 호출로 다년 전체 history 를
#   자동으로** 돌려준다 — 코드 변경 0(=사용자 요구: 결제 후 과거데이터가 최소수정으로 쓰임).
#   특정 구간만 원하면 ingest_tickers(start=date(...), end=date(...)) 인자로 좁히면 된다.
#   (룩어헤드 BLOCKING 은 호출부 책임 — 시점 t 결정엔 trade_date<=t 만.)
_DEMO_UNIVERSE: Final[tuple[tuple[str, Exchange], ...]] = (
    ("AAPL", Exchange.NASDAQ),  # 빅테크
    ("MSFT", Exchange.NASDAQ),
    ("NVDA", Exchange.NASDAQ),  # 반도체
    ("GOOGL", Exchange.NASDAQ),
    ("AMZN", Exchange.NASDAQ),
    ("META", Exchange.NASDAQ),
    ("JPM", Exchange.NYSE),  # 금융
    ("JNJ", Exchange.NYSE),  # 헬스케어
    ("XOM", Exchange.NYSE),  # 에너지
)


@dataclass(frozen=True, slots=True)
class TickerIngestResult:
    """종목 1건 적재 결과 — 행수·기간·거래소·에러(있으면).

    bar_count=0 + error=None 이면 데이터 부족(소스가 빈 결과 — 조용한 누락 아님, 명시 기록).
    error 가 채워지면 그 종목 fetch 가 실패했고 적재되지 않았다(부분 실패 명시).
    """

    ticker: str
    exchange: Exchange
    bar_count: int
    min_date: date | None
    max_date: date | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class IngestSummary:
    """적재 전체 요약 — 종목별 결과 + 최종 누적 검증 리포트(소실 탐지 게이트 결과).

    report 는 모든 종목 적재 후 누적 expected 로 검증한 최종 게이트다. report 가 None 이면 적재된
    종목이 하나도 없어(전부 0행/에러) 검증할 트리가 없는 경우다(명시 — 조용한 PASS 위장 금지).
    """

    results: tuple[TickerIngestResult, ...]
    report: VerificationReport | None

    @property
    def total_rows(self) -> int:
        return sum(r.bar_count for r in self.results)

    @property
    def ingested_ticker_count(self) -> int:
        """실제 1행 이상 적재된 종목 수(0행/에러 제외)."""
        return sum(1 for r in self.results if r.bar_count > 0)

    @property
    def empty_tickers(self) -> tuple[str, ...]:
        """데이터 부족(0행·에러 없음) 종목 — 생존편향 정량 고지용."""
        return tuple(r.ticker for r in self.results if r.bar_count == 0 and r.error is None)

    @property
    def failed_tickers(self) -> tuple[str, ...]:
        """fetch 에러로 적재 못 한 종목(부분 실패)."""
        return tuple(r.ticker for r in self.results if r.error is not None)

    @property
    def passed(self) -> bool:
        """전체 게이트 통과 여부 — 검증 PASS + 개별 fetch 에러 없음.

        report 가 None(적재 0종목)이면 PASS 아님(데이터셋 생성 실패). 부분 fetch 실패가 있어도
        PASS 아님(조용한 부분 누락 금지 — 실패 명확 보고).
        """
        return self.report is not None and self.report.passed and not self.failed_tickers


def ingest_tickers(
    source: DataSource,
    targets: Sequence[tuple[str, Exchange]],
    *,
    base_dir: Path = _DEFAULT_BASE_DIR,
    start: date | None = None,
    end: date | None = None,
) -> IngestSummary:
    """(ticker, exchange) 목록을 source 로 적재 → 누적 검증 → 집계 요약 반환(소스 무관).

    각 종목: `source.fetch_daily_bars(ticker, start, end)` → `write_daily_bars`(그 ticker 의
    exchange 파티션) → 누적 expected 로 `verify_parquet`. 누적 검증은 **이미 적재된 모든 종목**의
    기대 행수를 대조하므로, 어떤 종목 적재가 같은 파티션의 이전 종목을 소실시키면 시끄럽게 실패한다
    (TASK-B 소실탐지 — 생존편향 누수 봉인).

    ⚠️ 에러 정책(실패 명확 보고 BLOCKING):
    - 인증 실패(EodhdAuthError)·rate limit(EodhdRateLimitError)는 **전 종목 공통 원인**이므로
      즉시 전파한다(개별 종목 문제로 오인하면 나머지가 전부 같은 에러로 무의미 반복). 부분 결과는
      잃지 않게 이미 적재·검증된 것은 트리에 남아 있다(재실행 시 멱등 덮어쓰기).
    - 그 외 종목별 fetch 실패는 해당 종목 error 로 집계하고 다음 종목으로 진행(부분 실패 명시).
      단 그 경우 IngestSummary.passed=False 가 된다(조용한 부분 누락 금지).

    빈 결과(0행)는 적재 no-op 이라 expected 에 넣지 않는다(actual 0 과 정합 — 데이터 부족≠소실).
    적재된 종목이 하나도 없으면 report=None(검증할 트리 없음 — 명시).

    룩어헤드(BLOCKING)는 호출부 책임: 이 함수는 start/end 구간만 source 에 전달하며, 시점 t 결정에
    trade_date<=t 만 쓰는 것은 rules/backtest 단계가 보장한다(이 계약은 구간 필터만).
    """
    results: list[TickerIngestResult] = []
    cumulative_expected: dict[str, TickerExpectation] = {}
    any_ingested = False
    report: VerificationReport | None = None

    for ticker, exchange in targets:
        logger.info("적재 시작: ticker=%s, exchange=%s, source=%s", ticker, exchange, source.name)
        try:
            bars = source.fetch_daily_bars(ticker, start=start, end=end)
        except (EodhdAuthError, EodhdRateLimitError):
            # 전 종목 공통 원인 — 즉시 전파(나머지 무의미 반복 방지). 이미 적재된 건 트리 보존.
            ingested_so_far = sum(1 for r in results if r.bar_count > 0)
            logger.exception(
                "공통 원인 에러로 적재 중단: 마지막 ticker=%s, 누적 적재=%d종목",
                ticker,
                ingested_so_far,
            )
            raise
        except EodhdResponseError as exc:
            # 종목별 응답 오류(예: 잘못된 심볼·4xx/5xx)는 그 종목만 실패 집계하고 진행(부분 실패
            # 명시 — 조용한 누락 금지). status_code 만 기록(토큰 비노출은 어댑터가 보장). 이 경우
            # summary.passed=False 가 되어 데이터셋 신뢰 차단.
            logger.warning(
                "종목 적재 실패(응답 오류) — 건너뜀: ticker=%s, status=%s",
                ticker,
                exc.status_code,
            )
            results.append(
                TickerIngestResult(
                    ticker=ticker,
                    exchange=exchange,
                    bar_count=0,
                    min_date=None,
                    max_date=None,
                    error=f"EodhdResponseError(status={exc.status_code})",
                )
            )
            continue

        if not bars:
            # 0행 = 데이터 부족(소스가 빈 결과). 조용한 누락 아님 — 명시 기록·로그(추측 채움 금지).
            logger.warning(
                "적재 0행(데이터 부족, 소실 아님): ticker=%s, exchange=%s", ticker, exchange
            )
            results.append(
                TickerIngestResult(
                    ticker=ticker,
                    exchange=exchange,
                    bar_count=0,
                    min_date=None,
                    max_date=None,
                )
            )
            continue

        write_daily_bars(bars, exchange=exchange, base_dir=base_dir, source=source.name)
        any_ingested = True
        # 누적 기대 갱신 후 누적 검증 — 이전 종목 소실 시 여기서 VerificationError(시끄러운 실패).
        cumulative_expected.update(build_expected(bars))
        report = verify_parquet(base_dir, expected=cumulative_expected)

        dates = [b.trade_date for b in bars]
        results.append(
            TickerIngestResult(
                ticker=ticker,
                exchange=exchange,
                bar_count=len(bars),
                min_date=min(dates),
                max_date=max(dates),
            )
        )

    # 적재된 종목이 없으면(전부 0행) report 는 여전히 None — 명시 고지.
    if not any_ingested:
        logger.warning(
            "적재된 종목 0개(전부 데이터 부족) — 검증 트리 없음: targets=%d개", len(targets)
        )

    summary = IngestSummary(results=tuple(results), report=report)
    logger.info(
        "적재 완료: 종목=%d, 적재됨=%d, 빈종목=%d, 실패=%d, 총행수=%d, 게이트=%s",
        len(results),
        summary.ingested_ticker_count,
        len(summary.empty_tickers),
        len(summary.failed_tickers),
        summary.total_rows,
        "PASS" if summary.passed else "FAIL",
    )
    return summary


def _print_summary(summary: IngestSummary) -> None:
    """적재 요약을 사람이 읽는 표로 출력(진입점 — print 허용, logging-rules 예외)."""
    print("\n=== EODHD 미니 데이터셋 적재 결과 ===")
    print(f"{'ticker':<8}{'exchange':<10}{'bars':>6}  {'period':<25}{'status'}")
    for r in summary.results:
        period = f"{r.min_date}~{r.max_date}" if r.min_date else "(데이터 없음)"
        if r.error is not None:
            status = f"ERROR: {r.error}"
        elif r.bar_count == 0:
            status = "EMPTY"
        else:
            status = "OK"
        print(f"{r.ticker:<8}{r.exchange:<10}{r.bar_count:>6}  {period:<25}{status}")

    rep = summary.report
    print("\n--- 누적 검증 게이트 ---")
    if rep is None:
        print("검증 리포트 없음(적재된 종목 0개 — 데이터셋 생성 실패).")
    else:
        print(
            f"rows={rep.row_count}, tickers={rep.ticker_count}, "
            f"period={rep.min_date}~{rep.max_date}, dup={rep.duplicate_count}, "
            f"adj<=0={rep.nonpositive_adj_factor_count}, price<=0={rep.nonpositive_price_count}, "
            f"ohlc={rep.ohlc_violation_count}, "
            f"missing={len(rep.missing_tickers)}, shortfall={len(rep.shortfall_tickers)}"
        )
    if summary.empty_tickers:
        print(f"빈 종목(데이터 부족): {', '.join(summary.empty_tickers)}")
    if summary.failed_tickers:
        print(f"실패 종목(fetch 에러): {', '.join(summary.failed_tickers)}")
    print(f"\n총 행수={summary.total_rows}, 적재 종목={summary.ingested_ticker_count}")
    print(f"전체 게이트: {'PASS' if summary.passed else 'FAIL'}\n")


def main() -> int:
    """진입점. 로깅 가드·EodhdSource 주입·데모 8종목 적재·표 출력.

    ⚠️ configure_logging() 먼저 — EODHD 쿼리 인증(api_token)이 URL 에 실리므로 httpx INFO 로거가
    토큰 누출(logging-rules BLOCKING). 인증·rate limit 실패는 비0 종료(전 종목 공통 원인).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    configure_logging()
    source: DataSource = EodhdSource()
    try:
        summary = ingest_tickers(source, _DEMO_UNIVERSE)
    except EodhdAuthError:
        print("EODHD 인증 실패 — EODHD_API_KEY 확인 후 재실행하세요.", file=sys.stderr)
        return 2
    except EodhdRateLimitError:
        print("EODHD rate limit 초과(무료 20콜/일) — 한도 리셋 후 재실행하세요.", file=sys.stderr)
        return 3
    _print_summary(summary)
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
