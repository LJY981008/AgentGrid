"""라이브 파일럿 — Tiingo 실데이터로 저장층·수정주가(adj_factor)를 교차검증(M1 S3~S4).

`python -m stockpick.data.pilot` 로 실행. 자동 테스트가 아니다(라이브 API 호출). 컨테이너에서
`TIINGO_API_KEY` 가 주입된 상태로 별도 실행한다:

    docker compose exec -T app python -m stockpick.data.pilot

흐름: 알려진 소수 유니버스(ticker→exchange, **액면분할 표본 필수 포함**) 각각을
`TiingoSource.fetch_daily_bars(start=...)` → `storage.write_daily_bars` 적재 → `verify_parquet`
게이트 → **분할 직전 거래일의 adj_factor 교차검증** 표 출력.

⭐ 분할 교차검증 원리(수정주가 BLOCKING): adj_factor = adjClose/close 는 누적조정계수다. N:1 분할이
일어나면 분할 이전 모든 거래일의 adjClose 가 1/N 로 끌어내려지므로, **분할 직전 거래일의
adj_factor** 는 1/N 부근이어야 한다(배당 조정이 겹치면 정확히 1/N 은 아니나 분할 비율과 부합).
AAPL 4:1 → ≈0.25,
NVDA 10:1 → ≈0.1, TSLA 3:1 → ≈0.333. 부합하지 않으면 수정주가 정의가 깨진 것 → M1 게이트 실패 신호.

⚠️ 생존편향: 이 파일럿 유니버스는 현재 상장 종목 위주(무료 Tiingo 가 폐지종목 미제공 — 어댑터
iter_universe 가 NotImplementedError). 폐지 커버리지는 Sharadar SEP(M2)에서 보강한다(여기서 조용히
'전체'인 척하지 않는다 — 한계 명시).

⚠️ rate limit: Tiingo 무료는 시간당/일일 한도. 종목 간 짧은 지연을 두고, 429 발생 시 명확히 보고하고
중단한다(키 비노출). 키·민감정보는 로그·출력 어디에도 노출하지 않는다.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Final

from ..types import DailyBar, Exchange
from .source import DataSource
from .storage import (
    TickerExpectation,
    VerificationReport,
    build_expected,
    verify_parquet,
    write_daily_bars,
)
from .tiingo import TiingoRateLimitError, TiingoSource

logger = logging.getLogger(__name__)

_PILOT_START: Final = date(2018, 1, 1)
_SOURCE_LABEL: Final = "tiingo"
_INTER_REQUEST_DELAY_SEC: Final = 1.0  # 종목 간 지연(rate limit 여유)
_DEFAULT_BASE_DIR: Final = Path("data/parquet")


@dataclass(frozen=True, slots=True)
class PilotSymbol:
    """파일럿 종목 정의. split_date/split_ratio 는 분할 교차검증 대상(없으면 None)."""

    ticker: str
    exchange: Exchange
    note: str
    split_date: date | None = None
    split_ratio: int | None = None  # N:1 분할의 N (예: 4:1 → 4)


# 파일럿 유니버스 — 분할 표본 필수 포함(수정주가 교차검증). 분할일은 split-adjusted 효력 발생일.
_UNIVERSE: Final[tuple[PilotSymbol, ...]] = (
    PilotSymbol("AAPL", Exchange.NASDAQ, "4:1 분할(2020-08-31)", date(2020, 8, 31), 4),
    PilotSymbol("NVDA", Exchange.NASDAQ, "10:1 분할(2024-06-07)", date(2024, 6, 7), 10),
    PilotSymbol("TSLA", Exchange.NASDAQ, "3:1 분할(2022-08-25)", date(2022, 8, 25), 3),
    PilotSymbol("MSFT", Exchange.NASDAQ, "대형주(무분할 구간)"),
    PilotSymbol("JNJ", Exchange.NYSE, "대형주(배당주)"),
)


@dataclass(frozen=True, slots=True)
class SplitCheck:
    """분할 교차검증 1건 — 분할 직전 거래일의 adj_factor 실측 vs 기대(1/N)."""

    ticker: str
    split_date: date
    split_ratio: int
    prev_trade_date: date | None
    prev_adj_factor: Decimal | None
    expected_factor: Decimal


@dataclass(frozen=True, slots=True)
class SymbolResult:
    """종목별 파일럿 결과 — 적재 행수·기간·검증 리포트·분할 체크(있으면)."""

    ticker: str
    exchange: Exchange
    bar_count: int
    min_date: date | None
    max_date: date | None
    report: VerificationReport
    split_check: SplitCheck | None


def _compute_split_check(bars: list[DailyBar], symbol: PilotSymbol) -> SplitCheck | None:
    """분할 직전 거래일(split_date 미만 최댓값)의 adj_factor 를 뽑아 1/N 기대값과 비교 준비.

    bars 는 DailyBar 리스트(trade_date 오름차순 보장 안 함 → 여기서 필터·정렬). split_date 정의
    없으면 None. 분할 직전 거래일이 데이터에 없으면 prev_* = None(데이터 부족 — 보고만, 실패 아님).
    """
    if symbol.split_date is None or symbol.split_ratio is None:
        return None
    before = [b for b in bars if b.trade_date < symbol.split_date]
    expected = Decimal(1) / Decimal(symbol.split_ratio)
    if not before:
        return SplitCheck(
            ticker=symbol.ticker,
            split_date=symbol.split_date,
            split_ratio=symbol.split_ratio,
            prev_trade_date=None,
            prev_adj_factor=None,
            expected_factor=expected,
        )
    prev = max(before, key=lambda b: b.trade_date)
    return SplitCheck(
        ticker=symbol.ticker,
        split_date=symbol.split_date,
        split_ratio=symbol.split_ratio,
        prev_trade_date=prev.trade_date,
        prev_adj_factor=prev.adj_factor,
        expected_factor=expected,
    )


def run_pilot(
    *,
    source: DataSource,
    base_dir: Path = _DEFAULT_BASE_DIR,
    start: date = _PILOT_START,
    delay_sec: float = _INTER_REQUEST_DELAY_SEC,
) -> list[SymbolResult]:
    """파일럿 오케스트레이션. source 주입(테스트 가능) — 실행 진입점은 TiingoSource 주입.

    각 종목: fetch → 적재 → 검증 → 분할 체크. 429(rate limit)는 즉시 중단(부분 결과 반환,
    명확 로그). 빈 결과(데이터 없음)는 적재 no-op 후 0행 리포트(추측 채움 금지).

    ⭐ 소실 탐지(생존편향 BLOCKING): 파일럿은 base_dir 에 종목을 **누적** 적재하므로, i번째
    종목 적재 후 verify 에 넘기는 expected 는 0..i 까지 적재한 **누적 기대(ticker별 행수)** 다.
    이렇게 해야 같은 파티션의 이전 ticker 가 조용히 소실되면(라이브 회귀 버그) verify 가 누락으로
    시끄럽게 실패한다 — "현재 트리만 보던" 옛 약점을 봉인한다. 빈 결과(0행) ticker 는 expected 에
    넣지 않는다(적재되지 않으므로 actual 0 과 정합 — 추측 채움 금지). 0행은 데이터 부족이지 소실이
    아니다(소실은 적재됐던 ticker 가 사라지는 것).
    """
    results: list[SymbolResult] = []
    cumulative_expected: dict[str, TickerExpectation] = {}
    for i, symbol in enumerate(_UNIVERSE):
        if i > 0:
            time.sleep(delay_sec)
        logger.info("파일럿 수집 시작: ticker=%s (%s)", symbol.ticker, symbol.note)
        try:
            bars = source.fetch_daily_bars(symbol.ticker, start=start)
        except TiingoRateLimitError:
            logger.exception(
                "rate limit 으로 파일럿 중단: 마지막 ticker=%s, 누적 결과=%d종목",
                symbol.ticker,
                len(results),
            )
            raise

        write_daily_bars(
            bars,
            exchange=symbol.exchange,
            base_dir=base_dir,
            source=source.name,
        )
        # 누적 기대 갱신: 이 종목이 적재한 (ticker별) 행수를 합산. 빈 결과(0행)는 적재 no-op 이라
        # expected 에 넣지 않는다(actual 0 과 일치 — 데이터 부족≠소실). 같은 ticker 재등장 시 행수
        # 합산이지만 멱등 덮어쓰기로 actual 은 고유 (ticker,date) 집합 → 중복 게이트가 별도로 잡음.
        cumulative_expected.update(build_expected(bars))
        report = verify_parquet(base_dir, expected=cumulative_expected)

        dates = [b.trade_date for b in bars]
        results.append(
            SymbolResult(
                ticker=symbol.ticker,
                exchange=symbol.exchange,
                bar_count=len(bars),
                min_date=min(dates) if dates else None,
                max_date=max(dates) if dates else None,
                report=report,
                split_check=_compute_split_check(bars, symbol),
            )
        )
    return results


def _print_report(results: list[SymbolResult]) -> None:
    """파일럿 결과를 사람이 읽을 표로 출력(진입점 — print 허용, logging-rules 예외)."""
    print("\n=== 파일럿 종목별 적재 결과 ===")
    print(f"{'ticker':<8}{'exchange':<10}{'bars':>8}  {'period':<25}{'verify'}")
    for r in results:
        period = f"{r.min_date}~{r.max_date}" if r.min_date else "(데이터 없음)"
        verdict = "PASS" if r.report.passed else "FAIL"
        print(f"{r.ticker:<8}{r.exchange:<10}{r.bar_count:>8}  {period:<25}{verdict}")

    print("\n=== ⭐ 분할 수정주가 교차검증 (분할 직전 거래일 adj_factor) ===")
    print(
        f"{'ticker':<8}{'split':<14}{'prev_date':<13}"
        f"{'adj_factor(실측)':<24}{'기대(1/N)':<12}{'부합?'}"
    )
    for r in results:
        sc = r.split_check
        if sc is None:
            continue
        if sc.prev_adj_factor is None:
            print(f"{sc.ticker:<8}{f'{sc.split_ratio}:1':<14}{'(데이터 부족)':<13}")
            continue
        # 부합 판정: 실측 factor 가 기대 1/N 의 ±20% 이내면 OK(배당 조정·복수 분할 누적 허용 폭).
        lo = sc.expected_factor * Decimal("0.8")
        hi = sc.expected_factor * Decimal("1.2")
        ok = lo <= sc.prev_adj_factor <= hi
        actual = f"{sc.prev_adj_factor:.10f}"
        expected = f"{sc.expected_factor:.6f}"
        mark = "O" if ok else "X (점검!)"
        print(
            f"{sc.ticker:<8}{f'{sc.split_ratio}:1':<14}{str(sc.prev_trade_date):<13}"
            f"{actual:<24}{expected:<12}{mark}"
        )
    print()


def main() -> int:
    """진입점. 로깅 설정·TiingoSource 주입·실행·표 출력. rate limit·인증 실패는 비0 종료."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    source = TiingoSource()
    try:
        results = run_pilot(source=source)
    except TiingoRateLimitError:
        print("rate limit 초과로 파일럿 중단 — 한도 리셋 후 재실행하세요.", file=sys.stderr)
        return 2
    _print_report(results)
    all_passed = all(r.report.passed for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
