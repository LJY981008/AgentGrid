"""팩터 점수 → 순위 → TopEntry 리스트 — 랭킹 산출(stock-1st_plan §4.3 방식 A: 단일 점수 정렬).

이번 수직 슬라이스는 단일 팩터(모멘텀)라 §4.3 "방식 A(가중합 표준화 점수)"의 가장 단순한 형태 —
점수 내림차순 정렬 — 를 쓴다. 멀티팩터 순위합(방식 B)·필터후랭킹(방식 C)·정규화·가중치는 후속
(M2 백테스트가 조합·가중치를 결정 — §9-2). 이 모듈은 **순수 변환**이라 합성 점수로 단위 테스트한다.

랭킹 단위(§4.3): 한국은 코스피/코스닥 별도, 미국은 거래소별 또는 전체. 이 모듈은 group_by_exchange
플래그로 둘 다 지원한다(거래소별 = 시총·유동성 분포 차이로 통합 시 편중 회피 / 전체 = 소규모
데모처럼 종목이 적을 때). cik 는 데이터셋(EODHD)이 미제공이라 빈 문자열로 두고 ticker 로 식별
(후속 EDGAR 매핑 — types.TopEntry 주석·ADR-002 참조).

⚠️ 프로토타입 골격(§4.1): 산출된 랭킹은 백테스트 검증 전이므로 알파로 신뢰하지 않는다(과적합 경고).

모듈 경계(python-conventions): `rules` 는 `data`·`..types` 만 의존. 외부 의존 0(stdlib).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from ..types import Exchange, TopEntry

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .factors import MomentumScore

logger = logging.getLogger(__name__)

_FACTOR_NAME = "momentum"


def rank_by_momentum(
    scores: Mapping[str, MomentumScore],
    ticker_to_exchange: Mapping[str, Exchange],
    *,
    lookback_days: int,
    top_n: int,
    group_by_exchange: bool = False,
) -> list[TopEntry]:
    """모멘텀 점수 맵 → TopEntry 리스트(rank 1-based, 점수 내림차순). 산출 불가(score=None) 제외.

    파라미터:
      - scores: {ticker: MomentumScore}. score=None 종목은 랭킹에서 제외한다(데이터 부족 — 조용한
        포함 금지). 제외 사실은 집계 로그로 남긴다.
      - ticker_to_exchange: ticker → Exchange. TopEntry.exchange 채움·거래소별 그룹핑 키. 누락
        ticker 는 추측 채움 금지 — KeyError 대신 명시적 ValueError(실패 명확 보고).
      - top_n: 그룹(또는 전체)별 상위 N. 동점으로 N 경계가 갈리면 결정적 2차 키(ticker)로 절단.
      - group_by_exchange: True 면 거래소별 별도 랭킹(rank 가 거래소 안에서 1부터). False 면 전체
        통합 단일 랭킹.

    순위 규칙:
      - 1차 키 = score 내림차순(높을수록 1위). 2차 키 = ticker 오름차순(**결정적 동점 처리** — 같은
        실행은 항상 같은 순서. 재현성 BLOCKING).
      - rank 는 competition ranking(1,2,2,4): score 가 같으면 같은 rank 값을 부여(사용자에게 진짜
        동점을 드러냄). 단 리스트 순서·top_n 절단은 2차 키로 결정적.

    반환: rank 오름차순 정렬된 TopEntry 리스트(group_by_exchange 면 거래소별 블록을 이어붙임 —
    각 블록 내부는 rank 오름차순). 빈 입력·전부 None 이면 빈 리스트.
    """
    if top_n < 1:
        msg = f"top_n 은 1 이상이어야 함(받음={top_n})"
        raise ValueError(msg)

    rankable: list[tuple[str, MomentumScore]] = []
    skipped = 0
    for ticker, ms in scores.items():
        if ms.score is None:
            skipped += 1
            continue
        if ticker not in ticker_to_exchange:
            # 추측 채움 금지 — 거래소 미상 종목은 명시적 실패(어느 ticker 인지 보고).
            msg = (
                f"ticker_to_exchange 에 '{ticker}' 없음 — 거래소 미상으로 랭킹 불가(추측 금지). "
                "유니버스 정의와 점수 맵의 ticker 집합을 맞추세요."
            )
            raise ValueError(msg)
        rankable.append((ticker, ms))

    rule_version = f"v0-momentum-{lookback_days}"

    if group_by_exchange:
        groups: dict[Exchange, list[tuple[str, MomentumScore]]] = {}
        for ticker, ms in rankable:
            groups.setdefault(ticker_to_exchange[ticker], []).append((ticker, ms))
        entries: list[TopEntry] = []
        # 거래소 블록 순서도 결정적(Exchange 값 문자열 오름차순)으로 이어붙인다.
        for exchange in sorted(groups, key=lambda e: e.value):
            entries.extend(
                _rank_group(
                    groups[exchange],
                    ticker_to_exchange=ticker_to_exchange,
                    top_n=top_n,
                    rule_version=rule_version,
                )
            )
    else:
        entries = _rank_group(
            rankable,
            ticker_to_exchange=ticker_to_exchange,
            top_n=top_n,
            rule_version=rule_version,
        )

    logger.info(
        "랭킹 산출: 입력=%d, 랭킹가능=%d, 산출불가제외=%d, 엔트리=%d, top_n=%d, "
        "group_by_exchange=%s, rule_version=%s",
        len(scores),
        len(rankable),
        skipped,
        len(entries),
        top_n,
        group_by_exchange,
        rule_version,
    )
    return entries


def _rank_group(
    group: list[tuple[str, MomentumScore]],
    *,
    ticker_to_exchange: Mapping[str, Exchange],
    top_n: int,
    rule_version: str,
) -> list[TopEntry]:
    """한 그룹(거래소 또는 전체)을 점수 내림차순 정렬 → top_n 절단 → TopEntry 리스트.

    정렬 키: (-score, ticker) — score 내림차순, 동점은 ticker 오름차순(결정적). rank 는 competition
    ranking(동점은 같은 rank, 다음은 건너뜀). top_n 은 **리스트 위치** 기준 절단(동점이 경계를
    넘으면 2차 키로 결정적으로 잘림).
    """
    # score=None 은 상위(rank_by_momentum)에서 제외 확정이나 mypy 는 Optional 로 본다 — 여기서
    # 명시적으로 좁혀 (ticker, Decimal) 쌍으로 만든다(방어적 단언: None 유입은 버그로 시끄럽게).
    narrowed: list[tuple[str, Decimal]] = []
    for ticker, ms in group:
        if ms.score is None:
            msg = f"score=None 이 랭킹에 유입됨(버그): ticker={ticker}"
            raise RuntimeError(msg)
        narrowed.append((ticker, ms.score))

    # 결정적 정렬: score 내림차순 + ticker 오름차순(동점 안정). Decimal 비교로 정밀 손실 없음.
    ordered = sorted(narrowed, key=lambda item: (-item[1], item[0]))

    truncated = ordered[:top_n]
    entries: list[TopEntry] = []
    prev_score: Decimal | None = None
    current_rank = 0
    for position, (ticker, score) in enumerate(truncated, start=1):
        # competition ranking: 직전과 점수가 같으면 같은 rank, 다르면 위치값으로 갱신.
        if score != prev_score:
            current_rank = position
            prev_score = score
        entries.append(
            TopEntry(
                cik="",  # EODHD 미제공 — 후속 EDGAR 매핑(ticker 로 식별, types 주석 참조)
                ticker=ticker,
                exchange=ticker_to_exchange[ticker],
                rank=current_rank,
                # TopEntry.score=float 계약 — 표시·직렬화용(내부 계산은 Decimal)
                score=float(score),
                rule_version=rule_version,
                factors={_FACTOR_NAME: float(score)},
            )
        )
    return entries
