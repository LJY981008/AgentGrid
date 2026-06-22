"""프로덕션 포트 구현체 — Parquet/DuckDB(_scan 위임). 데모·실전이 주입한다.

⚠️ UniversePort(`PriceDerivedUniverse`): 무료 골격엔 종목마스터(listed/delisted)가 저장소에 없다
(EODHD 미제공). 가격 존재로 유니버스를 도출하면 survivorship 한계(미래상장 포함 불가·실폐지 미반영)
가 있으나, 골격 단계의 정직한 차선이다(data_caveats 에 한계 명시). 결제 후 종목마스터(TASK-E/S5)·
ticker_history 적재 시 listed/delisted 기반 정식 UniversePort 로 교체한다. 합성 폐지 주입이 필요한
테스트는 `fakes.FakeUniversePort` 를 쓴다(프로덕션 경로와 분리).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

from ..rules import _scan

if TYPE_CHECKING:
    from pathlib import Path

    from ..rules._scan import PricePoint
    from ..types import Exchange
    from .ports import PriceSeriesPort, UniversePort

logger = logging.getLogger(__name__)

_SNAPSHOT_NAME = "stock_snapshot.json"


class ParquetPriceSeriesPort:
    """daily_bar Parquet → 수정주가 시계열(_scan 위임). full_series 는 as_of=None 전구간."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._full: dict[str, list[PricePoint]] | None = None

    def load(self, *, as_of: date) -> dict[str, list[PricePoint]]:
        return _scan.load_adjusted_series(self._base_dir, as_of=as_of)

    def full_series(self) -> dict[str, list[PricePoint]]:
        if self._full is None:
            self._full = _scan.load_adjusted_series(self._base_dir, as_of=None)
        return self._full

    def trading_days(self) -> list[date]:
        # full_series 전체 메모리 로드(OOM) 대신 DuckDB DISTINCT 집계(_scan.load_trading_days).
        return _scan.load_trading_days(self._base_dir)

    def ticker_exchanges(self) -> dict[str, Exchange]:
        return _scan.load_ticker_exchanges(self._base_dir)


class PriceDerivedUniverse:
    """가격 존재로 유니버스 도출 — listed=첫 거래일, 폐지 없음. ⚠️ survivorship 한계(실폐지 미반영).

    골격(무료) 전용 차선: 종목마스터(listed/delisted) 부재 시 가격 시계열의 첫 거래일을 상장일로
    간주한다. 미래상장 배제·실폐지 청산은 못 하므로(data_caveats 고지), 결제 후 종목마스터 기반
    UniversePort 로 교체한다. UniversePort Protocol(constituents·delisting_event) 구현.
    """

    def __init__(self, price_port: PriceSeriesPort) -> None:
        self._listed = {
            ticker: pts[0].trade_date for ticker, pts in price_port.full_series().items() if pts
        }

    def constituents(self, *, as_of: date) -> set[str]:
        return {ticker for ticker, listed_at in self._listed.items() if listed_at <= as_of}

    def delisting_event(self, ticker: str) -> date | None:  # noqa: ARG002 (가격기반엔 폐지 정보 없음)
        return None

    def ticker_count(self) -> int:
        """도출된 종목 수(데모 top_n·리포트용)."""
        return len(self._listed)


class MasterUniverse:
    """종목마스터 스냅샷(`stock_snapshot.json`) 기반 시점 유니버스 — 생존편향+룩어헤드-correct.

    `constituents(as_of)` = `listed_at<=as_of AND (boundary None OR as_of<boundary)`
    — FakeUniversePort 와 **동일 규약**(`as_of<boundary`)이되 **입력 의미가 다르다**: Fake 의
    `delisted` 인자는 이미 "첫 거래불가일"이고, 스냅샷 `delisted_at`(마지막 실거래일)은 `+1day`
    변환 후 그 규약에 들어간다(같은 boundary 를 주면 동일 결과 — formula 동일이 아님·`+1day` 제거
    금지). ⚠️ **경계 변환(BLOCKING)**: 스냅샷
    `delisted_at`=마지막 실거래일(추정)인데 engine/Fake/Protocol 은 경계를 "첫 거래불가일"로
    해석(`_price_before(de)`=de 직전 마지막 봉) → 로드 시 `boundary = delisted_at + 1day` 로
    변환해야 마지막 실거래일이 거래가능으로 유지되고(constituents) 청산가가 마지막 실봉이 된다
    (`delisting_event`=boundary → engine `_price_before(boundary)`=마지막 실봉). engine/ports/
    fakes 불변 — 변환은 이 어댑터 내부에만.

    ⚠️ `listed_at None`(가격 없는 마스터 종목)·degenerate(`listed_at>=delisted_at`) 행은 제외
    (조용한 소실 금지 — degenerate 는 WARNING). UniversePort Protocol 구현.
    """

    def __init__(self, base_dir: Path) -> None:
        payload = json.loads((base_dir / _SNAPSHOT_NAME).read_text(encoding="utf-8"))
        self._membership: dict[str, tuple[date, date | None]] = {}
        dropped = no_price = 0
        for s in payload["stocks"]:
            # 외부 입력(JSON) 경계 검증 — isinstance 로 Any 흐름 차단(python-conventions §타입).
            ticker = str(s["ticker"])
            listed_raw = s["listed_at"]
            if not isinstance(listed_raw, str):
                no_price += 1  # listed_at 부재(가격 없는 마스터 종목) — 거래 불가, 제외(방어적)
                continue
            delisted_raw = s["delisted_at"]
            listed = date.fromisoformat(listed_raw)
            delisted = date.fromisoformat(delisted_raw) if isinstance(delisted_raw, str) else None
            if delisted is not None and listed >= delisted:
                dropped += 1  # degenerate(하루도 거래 불가) — 조용한 소실 금지
                continue
            boundary = delisted + timedelta(days=1) if delisted is not None else None
            self._membership[ticker] = (listed, boundary)
        self._dropped_degenerate = dropped  # 관측성 — 호출부/테스트가 읽어 caveat 반영 가능
        if dropped:
            logger.warning("MasterUniverse degenerate(listed>=delisted) %d종목 제외", dropped)
        if no_price:
            logger.info("MasterUniverse listed_at 부재 %d종목 제외(가격 없는 마스터)", no_price)

    def constituents(self, *, as_of: date) -> set[str]:
        return {
            ticker
            for ticker, (listed, boundary) in self._membership.items()
            if listed <= as_of and (boundary is None or as_of < boundary)
        }

    def delisting_event(self, ticker: str) -> date | None:
        m = self._membership.get(ticker)
        return m[1] if m is not None else None

    def ticker_count(self) -> int:
        """유니버스 멤버십 종목 수(데모 top_n·리포트용)."""
        return len(self._membership)


def _select_universe(base_dir: Path, price_port: PriceSeriesPort) -> UniversePort:
    """스냅샷 존재 시 MasterUniverse(생존편향-correct)·부재 시 PriceDerivedUniverse(골격 폴백).

    ⚠️ 부재→폴백은 WARNING(생존편향 미방어 상태가 조용히 지속되는 anti-pattern 방지).
    """
    if (base_dir / _SNAPSHOT_NAME).is_file():
        logger.info("유니버스=MasterUniverse(stock_snapshot.json·생존편향-correct 멤버십)")
        return MasterUniverse(base_dir)
    logger.warning(
        "유니버스=PriceDerivedUniverse 폴백 — stock_snapshot.json 부재(생존편향 미방어·골격). "
        "MasterUniverse 쓰려면 `bulk --finalize` 로 스냅샷 생성"
    )
    return PriceDerivedUniverse(price_port)
