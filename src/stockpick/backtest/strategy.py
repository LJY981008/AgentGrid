"""포트폴리오 구성 전략 — 플러그인(Strategy Protocol). 랭킹 결과 → cik별 비중(합=1, Decimal)."""

from __future__ import annotations

import math
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


class TopDecileEqualWeight:
    """상위 decile 등가중(ADR-010 #3) — 랭킹된 후보 풀 상위 `pct`(종목수 가변·floor 가드) 등가중.

    표준 momentum 검증 포트(JT 2001류 decile). 입력 `ranked` = **유동성 필터 통과 후 momentum 랭킹된
    전 후보**(rank 오름차순). 보유수 = `clamp(max(min_holdings, ceil(pct×N)), 1, N)` — `pct×N` 올림
    (부분 종목 없음)·소형/초기 유니버스는 `min_holdings` floor 로 과집중 방지·전체보다 클 순 없음.
    분모 N = 후보 수(전체 유니버스 아님·M1). top-5 고정(EqualWeightTopN)과 별도 룰 정체성(name).

    ⚠️ `ranked` 가 평면 단일 랭킹임을 전제(group_by_exchange=False·게이트 정규값). 거래소별 그룹핑
    리스트면 '이어붙인 리스트 상위 pct'(블록 편중)라 decile 의미가 흐려진다 — 정규 게이트는 평면
    랭킹이라 무방(엔진이 decile 모드선 group 평면 가정).
    """

    name = "top_decile_equal_weight"

    def __init__(self, *, pct: Decimal, min_holdings: int) -> None:
        self._pct = pct
        self._min_holdings = min_holdings

    def weights(self, ranked: list[TopEntry], *, as_of: date) -> dict[str, Decimal]:  # noqa: ARG002
        if not ranked:
            return {}
        n_total = len(ranked)
        # pct×N 올림(부분 종목 없음) → floor 와 max → 전체 cap. Decimal×int=Decimal·ceil=int.
        n = max(self._min_holdings, math.ceil(self._pct * Decimal(n_total)))
        n = min(n, n_total)
        selected = ranked[:n]
        w = Decimal(1) / Decimal(len(selected))
        return {_key(e): w for e in selected}


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
