"""룰엔진 데모 — `data/parquet` 수정주가 → 모멘텀 → Top 랭킹 출력(`python -m stockpick.rules`).

수직 슬라이스 시연: Parquet 스캔(_scan) → 모멘텀 산출(factors) → 랭킹(ranking) → TopEntry 표 출력.
⚠️ 9종목·1년치(251 거래일) 프로토타입이다 — 장기 백테스트가 아니라 **골격 입증용**이다. 산출 랭킹은
백테스트(M2 §4.4) 검증 전이므로 알파로 신뢰하지 않는다(stock-1st_plan §4.1 과적합 경고).

룩어헤드(BLOCKING): as_of 를 데이터 최신일로 잡고, _scan 이 trade_date<=as_of 만 로드, factors 가
한 번 더 필터한다(2중 방어선). 기본 룩백 126 거래일(≈6개월)·최근 21 거래일(≈1개월) 제외(reversal
회피 — §4.2 표준 관행). 이 값들도 후보일 뿐 최종은 백테스트가 결정한다.

진입점이므로 print 허용(logging-rules 예외). 라이브러리 코드(_scan·factors·ranking)는 print 없음.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Final

from ..data import configure_logging  # rules→data 의존 허용(모듈 경계: 하위만 import)
from ..types import Exchange, TopEntry
from ._scan import load_adjusted_series, load_ticker_exchanges
from .factors import momentum_universe
from .ranking import rank_by_momentum

if TYPE_CHECKING:
    from datetime import date

    from .factors import MomentumScore

logger = logging.getLogger(__name__)

_DEFAULT_BASE_DIR: Final = Path("data/parquet")
# 후보 파라미터(백테스트 미검증 — §4.1). 126 거래일≈6개월 룩백, 21 거래일≈1개월 제외(reversal 회피).
_DEFAULT_LOOKBACK_DAYS: Final = 126
_DEFAULT_SKIP_RECENT_DAYS: Final = 21
_DEFAULT_TOP_N: Final = 5


def run_demo(
    *,
    base_dir: Path = _DEFAULT_BASE_DIR,
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    skip_recent_days: int = _DEFAULT_SKIP_RECENT_DAYS,
    top_n: int = _DEFAULT_TOP_N,
    group_by_exchange: bool = True,
) -> int:
    """데모 실행 — 스캔→모멘텀→랭킹→표 출력. 반환=프로세스 종료코드(0=정상, 1=데이터 없음).

    as_of 는 데이터셋 최신 거래일로 자동 설정한다(전 종목 공통 최신일). 데이터가 없으면 1.
    """
    series = load_adjusted_series(base_dir, as_of=None)
    if not series:
        print(f"데이터 없음 — Parquet 트리 비어있음: {base_dir}/daily_bar")
        return 1

    # as_of = 데이터셋 전체 최신 거래일. 이후 factors 가 as_of 이하만 사용(룩어헤드 2차 방어).
    as_of = max(p.trade_date for pts in series.values() for p in pts)

    ticker_to_exchange = load_ticker_exchanges(base_dir)
    scores = momentum_universe(
        series,
        as_of=as_of,
        lookback_days=lookback_days,
        skip_recent_days=skip_recent_days,
    )
    entries = rank_by_momentum(
        scores,
        ticker_to_exchange,
        lookback_days=lookback_days,
        top_n=top_n,
        group_by_exchange=group_by_exchange,
    )
    _print_ranking(
        entries,
        scores=scores,
        as_of=as_of,
        lookback_days=lookback_days,
        skip_recent_days=skip_recent_days,
        top_n=top_n,
        group_by_exchange=group_by_exchange,
    )
    return 0


def _print_ranking(
    entries: list[TopEntry],
    *,
    scores: dict[str, MomentumScore],
    as_of: date,
    lookback_days: int,
    skip_recent_days: int,
    top_n: int,
    group_by_exchange: bool,
) -> None:
    """랭킹 결과를 사람이 읽는 표로 출력(진입점 — print 허용)."""
    print("\n=== M2 룰엔진 수직 슬라이스 — 모멘텀 Top 랭킹 (프로토타입) ===")
    print(
        f"as_of={as_of}, 룩백={lookback_days}거래일, 최근제외={skip_recent_days}거래일, "
        f"top_n={top_n}, 거래소별={group_by_exchange}"
    )
    print("⚠️ 9종목·1년치 프로토타입 — 백테스트 미검증(알파 아님, §4.1 과적합 경고)\n")

    # 산출 불가(데이터 부족) 종목 정량 고지(조용한 누락 금지).
    unrankable = sorted(t for t, s in scores.items() if s.score is None)
    if unrankable:
        print(f"산출 불가(데이터 부족) 종목 {len(unrankable)}개: {', '.join(unrankable)}\n")

    header = f"{'rank':>4}  {'ticker':<8}{'exchange':<10}{'momentum':>12}  기간(start~end)"
    print(header)
    print("-" * 60)
    prev_exchange: Exchange | None = None
    for entry in entries:
        if group_by_exchange and entry.exchange != prev_exchange:
            if prev_exchange is not None:
                print()
            prev_exchange = entry.exchange
        ms = scores[entry.ticker]
        period = f"{ms.start_date}~{ms.end_date}" if ms.start_date else "(부족)"
        pct = entry.score * 100  # 비율→% 표시(내부 계약은 비율 소수)
        print(f"{entry.rank:>4}  {entry.ticker:<8}{entry.exchange:<10}{pct:>10.2f}%  {period}")
    print(f"\n총 엔트리={len(entries)} (rule_version 예: v0-momentum-{lookback_days})\n")


def main() -> int:
    """진입점. 로깅 설정(logging-rules 규약)·데모 실행."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    configure_logging()
    return run_demo()


if __name__ == "__main__":
    raise SystemExit(main())
