"""프로덕션 포트 구현체 — Parquet/DuckDB(_scan 위임). 데모·실전이 주입한다.

UniversePort: 무료 골격엔 종목마스터(listed/delisted)가 저장소에 없다(EODHD 미제공). 가격파일
존재로 유니버스를 도출하면 survivorship 결함(미래상장 포함·폐지 자동제외)이므로, 프로덕션
UniversePort 는 종목마스터 적재(TASK-E/S5) 후 구현한다 — 그 전엔 데모가 fakes 를 쓰고 한계를
data_caveats 에 명시한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..rules import _scan

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from ..rules._scan import PricePoint


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
