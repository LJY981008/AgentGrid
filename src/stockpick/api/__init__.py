"""api 모듈 — FastAPI HTTP 층(M3). data·rules·types 를 조합해 프론트(PWA)에 노출(읽기 위주).

모듈 경계(python-conventions): api 는 **상위** 모듈 — data·rules·backtest·types 를 import 하되,
하위는 api 를 import 하지 않는다. 계산은 전부 하위(rules/data)에 위임하며(서버 단일 진실), api 는
직렬화·경계 검증·에러 매핑만 한다. 금융 BLOCKING(룩어헤드·생존편향·미검증 경고)은 하위가 강제.

`app` 노출: `uvicorn stockpick.api:app` 또는 `python -m stockpick.api`(__main__) 로 기동.
"""

from __future__ import annotations

from .app import app, create_app

__all__ = ["app", "create_app"]
