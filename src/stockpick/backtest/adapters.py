"""프로덕션 포트 구현체 — Parquet/DuckDB(_scan 위임). 데모·실전이 주입한다.

⚠️ UniversePort(`PriceDerivedUniverse`): 무료 골격엔 종목마스터(listed/delisted)가 저장소에 없다
(EODHD 미제공). 가격 존재로 유니버스를 도출하면 survivorship 한계(미래상장 포함 불가·실폐지 미반영)
가 있으나, 골격 단계의 정직한 차선이다(data_caveats 에 한계 명시). 결제 후 종목마스터(TASK-E/S5)·
ticker_history 적재 시 listed/delisted 기반 정식 UniversePort 로 교체한다. 합성 폐지 주입이 필요한
테스트는 `fakes.FakeUniversePort` 를 쓴다(프로덕션 경로와 분리).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..rules import _scan

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from ..rules._scan import PricePoint
    from ..types import Exchange
    from .ports import PriceSeriesPort


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
        return sorted({p.trade_date for pts in self.full_series().values() for p in pts})

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
