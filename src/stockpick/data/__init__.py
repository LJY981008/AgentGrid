"""data 모듈 — M1+ 구현(수집·저장·정규화).

진입점 공통 로깅 가드(`configure_logging`)를 노출한다. 어댑터 코드(eodhd 등)는 핸들러·레벨을
건드리지 않으며(logging-rules: 설정은 진입점 1회), 진입점이 이 헬퍼를 basicConfig 직후 호출한다.
"""

from __future__ import annotations

import logging
from typing import Final

# httpx 라이브러리 자체 INFO 로거는 토큰이 실린 *완성 URL* 을 로깅한다(EODHD 는 ?api_token
# 쿼리 인증이라 토큰이 URL 에 실림 — 어댑터 내부에서 끌 수 없는 라이브러리 동작). WARNING 이상으로
# 올려 INFO URL 로그를 막는다.
_TOKEN_LEAKING_LOGGERS: Final = ("httpx", "httpcore")


def configure_logging() -> None:
    """진입점용 로깅 가드 — 토큰 누출 로거(httpx 등)를 WARNING 으로 올린다(logging-rules BLOCKING).

    ⚠️ 왜 코드화하나: EODHD 인증은 `?api_token=<KEY>` 쿼리라 토큰이 완성 URL 에 실린다. 우리 어댑터
    로거는 토큰/URL 을 안 남기지만 `httpx`/`httpcore` 의 INFO 로거는 완성 URL(토큰 포함)을 로깅한다.
    이를 진입점마다 손으로 막으면 빠뜨리기 쉬우므로(누락 시 키 누출), 이 헬퍼 한 곳에 모은다.

    진입점(예: pilot.main)이 `logging.basicConfig(...)` 직후 1회 호출한다. 라이브러리 코드에서는
    호출하지 않는다(설정은 진입점 책임).
    """
    for name in _TOKEN_LEAKING_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
