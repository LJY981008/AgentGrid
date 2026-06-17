"""IdentityResolver 구현체 — ticker→cik 해소(생존편향 앵커).

`EdgarSnapshotResolver`: `data.edgar` 가 저장한 **현재 스냅샷**(`base_dir/edgar/ticker_cik.json`)을
읽어 ticker→cik 를 해소한다. `on`(시점)은 무시 — 현재 매핑만(폐지·과거 티커 미수록). 결제 후
시점별 `TickerHistoryResolver`(SEC submissions 이력·생존편향 정답)가 같은 Protocol 로 추가되며,
그때 `on` 을 사용한다. 엔진·api 는 Protocol(`cik_for`)만 의존 → 구현 교체는 DI(코드 0 변경).

미해소 ticker(저장본에 없음·미적재) → 빈 문자열(조용한 추측 금지 — 기존 계약). 저장본 부재면 빈 맵
→ 전부 ""(현 동작 유지·에러 아님).

모듈 경계: `backtest` 는 `data`(저장본 읽기)·`..types` 만 의존. 라이브 SEC 호출 안 함(저장본만).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..data.edgar import load_ticker_cik

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

logger = logging.getLogger(__name__)


class EdgarSnapshotResolver:
    """현재 ticker→cik 스냅샷 기반 IdentityResolver. 생성자에서 저장본 1회 로드(재read 없음)."""

    def __init__(self, base_dir: Path) -> None:
        self._map = load_ticker_cik(base_dir)
        logger.info("EdgarSnapshotResolver 로드: ticker→cik %d건", len(self._map))

    def cik_for(self, ticker: str, *, on: date) -> str:  # noqa: ARG002 (on=시점, 스냅샷은 무시)
        """ticker(대문자 정규화) → cik. 미해소면 "". `on` 무시(현재 스냅샷 — history 는 후속)."""
        return self._map.get(ticker.upper(), "")
