"""재무 fact 의 PIT(point-in-time) 접근 — 저장본 로드 + 시점 선택(룩어헤드 1차 방어선).

가격의 `_scan`(DuckDB SQL `trade_date<=as_of` 가드)에 대응하는 **재무 버전**이다. 재무는
companyfacts 슬라이스(`data/edgar.load_financials`)로 작은 규모라 DuckDB 없이 메모리 리스트에서
필터한다. 이 모듈이 재무 PIT 선택의 **단일 출처** — factors 는 여기로만 fact 를 고른다.

⚠️ 룩어헤드 BLOCKING(재무): 시점 as_of 의 값은 **disclosed_at(=EDGAR `filed`, 공시일) <= as_of**
인 fact 만 쓴다. 회계기간 말(`period_end`=EDGAR `end`)이 as_of 이하라도 그 공시(filed)가 as_of
이후면 **미래 정보 누설**이다(재무는 분기말 후 수주~수개월 뒤 공시). 가드는 period_end 가 아니라
disclosed_at 기준 — `latest_as_of` 가 강제한다(test_financials sabotage 가 회귀 봉인).

모듈 경계(python-conventions): `rules` 는 `data`·`..types` 만 의존. 이 파일은 `..data.edgar`(저장본
읽기)·`..types`(FinancialFact) 의존 — 외부 네트워크/DuckDB 없음(순수 메모리 선택).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..data.edgar import load_financials

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date
    from pathlib import Path

    from ..types import FinancialFact

logger = logging.getLogger(__name__)

_ANNUAL_SUFFIX = "-FY"  # fiscal_period 가 "{fy}-FY" 면 연간(10-K) — 분기(Q1~Q3) 제외용


def load_financial_facts(base_dir: Path) -> list[FinancialFact]:
    """저장된 재무 fact 로드 — **Parquet(A3 백필) 우선·JSON 폴백**. 미적재면 빈 리스트(에러 아님).

    A3 이후 운영본은 `financial_fact/<CIK>.parquet`(만-cik). Parquet 있으면 그걸, 없으면(파일럿·
    미마이그레이션) 구 `edgar/financials.json` 폴백. `latest_as_of` PIT(disclosed_at<=as_of) 불변.
    """
    from ..data.storage import load_financial_facts as _load_parquet

    facts = _load_parquet(base_dir)
    if facts:
        logger.info("재무 fact 로드(Parquet): %d건 (base_dir=%s)", len(facts), base_dir)
        return facts
    facts = load_financials(base_dir)  # JSON 폴백(파일럿 슬라이스·Parquet 미적재)
    logger.info("재무 fact 로드(JSON 폴백): %d건 (base_dir=%s)", len(facts), base_dir)
    return facts


def latest_as_of(
    facts: Iterable[FinancialFact],
    *,
    concept: str,
    cik: str,
    as_of: date,
    annual_only: bool = False,
) -> FinancialFact | None:
    """PIT 선택: `disclosed_at <= as_of` 인 (cik, concept) fact 중 회계기간 최신 1건.

    룩어헤드 BLOCKING: disclosed_at(EDGAR filed)<=as_of 만 — period_end(회계기간말)가 아니라
    공시일 기준(공시 시차로 미래 누설 차단). 회계기간 최신 = max(period_end); 동률(정정공시)이면
    disclosed_at 최신(amendment 우선, 원본은 보존되나 최신값 사용). annual_only 면 연간(10-K,
    fiscal_period "-FY")만 — 분기 제외(연간 ROE 기준). 해당 fact 없으면 None.
    """
    eligible = [
        f
        for f in facts
        if f.cik == cik
        and f.concept == concept
        and f.disclosed_at <= as_of
        and (not annual_only or f.fiscal_period.endswith(_ANNUAL_SUFFIX))
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda f: (f.period_end, f.disclosed_at))
