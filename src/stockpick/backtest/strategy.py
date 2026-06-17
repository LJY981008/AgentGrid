"""포트폴리오 구성 전략 — 플러그인(Strategy Protocol). 랭킹 결과 → cik별 비중(합=1, Decimal)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    from ..types import TopEntry


def _key(entry: TopEntry) -> str:
    """비중 키 = cik(앵커). 미제공(빈 문자열)이면 ticker 폴백(데이터 한계 — caveat 대상)."""
    return entry.cik or entry.ticker


@runtime_checkable
class Strategy(Protocol):
    """랭킹된 TopEntry → {key: weight Decimal}(합=1). 순수 — 데이터·시간 의존 없음."""

    @property
    def name(self) -> str: ...

    def weights(self, ranked: list[TopEntry], *, as_of: date) -> dict[str, Decimal]: ...


class EqualWeightTopN:
    """동일가중 — 각 종목 1/N(§5 분산투자). 가장 단순·과적합 방어."""

    name = "equal_weight_top_n"

    def weights(self, ranked: list[TopEntry], *, as_of: date) -> dict[str, Decimal]:
        if not ranked:
            return {}
        w = Decimal(1) / Decimal(len(ranked))
        return {_key(e): w for e in ranked}


class ScoreWeightTopN:
    """점수가중 — 양수 점수 비례. 점수합<=0 이면 동일가중 폴백(음수 비중 금지)."""

    name = "score_weight_top_n"

    def weights(self, ranked: list[TopEntry], *, as_of: date) -> dict[str, Decimal]:
        if not ranked:
            return {}
        scores = {_key(e): Decimal(str(e.score)) for e in ranked}
        total = sum((s for s in scores.values() if s > 0), Decimal(0))
        if total <= 0:
            w = Decimal(1) / Decimal(len(ranked))
            return dict.fromkeys(scores, w)
        return {k: (s / total if s > 0 else Decimal(0)) for k, s in scores.items()}
