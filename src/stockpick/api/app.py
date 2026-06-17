"""FastAPI 앱 조립 — CORS·라우터 등록·startup(configure_logging)·학습 이미지 정적 마운트.

모듈 경계(python-conventions): api 는 상위 모듈 — data·rules·types 를 조합만 하고, 하위는 api 를
import 하지 않는다. BLOCKING(룩어헤드·생존편향·미검증 경고)은 하위(rules/data)가 이미 강제하며 api
는 위임·노출만 한다.

startup: configure_logging() 1회 — httpx/httpcore INFO 로거를 WARNING 으로 올려 EODHD 토큰이 실린
완성 URL 로깅을 차단한다(logging-rules BLOCKING). ingest 라우트도 방어적으로 재호출한다.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..data import configure_logging
from .deps import get_cors_origins, get_learning_dir
from .routes import dataset, health, ingest, learning, ranking

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """FastAPI 인스턴스 생성·구성. 테스트는 이 함수로 앱을 만들어 dependency_overrides 를 건다."""
    configure_logging()

    app = FastAPI(
        title="stockpick API",
        version="0.0.1",
        description="개인 투자용 미국 주식 분석 — 수집·랭킹·학습 노출(읽기 위주). "
        "⚠️ 랭킹은 백테스트 검증 전(§4.1) — 알파 아님.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        allow_credentials=False,  # 개인용·쿠키 인증 없음
    )

    api_routers = (health.router, dataset.router, ingest.router, ranking.router, learning.router)
    for router in api_routers:
        app.include_router(router, prefix="/api")

    # 학습 이미지(112개) 정적 서빙. 디렉토리 부재(마운트 누락)면 마운트 생략 + 경고(앱은 기동).
    learning_dir = get_learning_dir()
    if learning_dir.is_dir():
        app.mount(
            "/learning-assets",
            StaticFiles(directory=str(learning_dir)),
            name="learning-assets",
        )
    else:
        logger.warning(
            "학습 디렉토리 없음 — /learning-assets 마운트 생략(이미지 404): dir=%s", learning_dir
        )

    logger.info("FastAPI 앱 구성 완료: CORS origins=%s", get_cors_origins())
    return app


app = create_app()
