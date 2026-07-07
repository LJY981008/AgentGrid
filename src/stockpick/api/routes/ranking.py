"""GET /api/ranking — Top 모멘텀 랭킹(얇은 라우트 — 오케스트레이션은 ranking_service).

산출 흐름 전체는 `api/ranking_service.compute_ranking`(M4 P6 행위 보존 추출) — 추적 라운드
스냅샷 캡처(POST /api/rounds)와 공유하는 단일 출처. 여기는 Query 검증(422·ge/Literal)과
DI 만 담당한다.

⭐ §4.1 BLOCKING: meta.validated=false + warning 상시(서비스가 보장 — S6-b 게이트 판정만 flip).
룩어헤드(BLOCKING)는 하위 강제: as_of 지정 시 load_adjusted_series trade_date<=as_of 1차 가드.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003 — FastAPI Query 런타임 타입
from pathlib import Path  # noqa: TC003 — Depends 런타임 타입
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, Depends, Query

from ..deps import get_base_dir, get_identity_resolver
from ..models import RankingResponse
from ..ranking_service import compute_ranking

if TYPE_CHECKING:
    from ...backtest.ports import IdentityResolver

router = APIRouter()


@router.get("/ranking", response_model=RankingResponse)
def ranking(
    base_dir: Path = Depends(get_base_dir),
    as_of: date | None = Query(default=None, description="평가 시점(ISO). 미지정=최신일"),
    lookback_days: int = Query(default=126, ge=1, description="룩백 거래일 수"),
    skip_recent_days: int = Query(default=21, ge=0, description="최근 N거래일 제외(reversal 회피)"),
    top_n: int = Query(default=5, ge=1, description="그룹(또는 전체)별 상위 N"),
    group: Literal["exchange", "all"] = Query(default="exchange", description="랭킹 단위"),
    identity: IdentityResolver = Depends(get_identity_resolver),
) -> RankingResponse:
    return compute_ranking(
        base_dir,
        identity,
        as_of=as_of,
        lookback_days=lookback_days,
        skip_recent_days=skip_recent_days,
        top_n=top_n,
        group=group,
    )
