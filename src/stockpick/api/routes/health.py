"""GET /api/health — 생존 신호 + 패키지 버전.

version 은 설치된 패키지 메타데이터에서 읽는다(pyproject 0.0.1). 메타데이터 조회 실패 시 "unknown"
(예외 메시지·내부 경로 비노출 — 키 비노출 원칙과 동일하게 상세를 client 에 흘리지 않음).
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

from ..models import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        pkg_version = version("stockpick")
    except PackageNotFoundError:
        # 메타데이터 부재(비정상 설치)는 명시 기록하되 client 엔 "unknown"(내부 상세 비노출).
        logger.warning("패키지 메타데이터 조회 실패 — version=unknown 으로 응답")
        pkg_version = "unknown"
    return HealthResponse(status="ok", version=pkg_version)
