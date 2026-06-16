"""data.configure_logging 회귀 테스트 — httpx 토큰 URL 누출 가드 코드화(TASK-D).

EODHD 는 ?api_token 쿼리 인증이라 httpx 라이브러리 INFO 로거가 토큰 실린 완성 URL 을 로깅한다
(어댑터 내부에서 끌 수 없음 — 진입점 책임). configure_logging() 이 그 로거 레벨을 WARNING 으로
올려 INFO URL 로그를 막는지 고정한다.
"""

from __future__ import annotations

import logging

from stockpick.data import configure_logging


def test_configure_logging_raises_httpx_logger_level_to_warning() -> None:
    """httpx/httpcore 로거 레벨이 WARNING 이상으로 설정돼 INFO(토큰 URL) 로그가 차단된다."""
    # 사전에 INFO 로 낮춰 두고(누출 가능 상태) 가드가 되돌리는지 확인.
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)

    configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    # INFO 레코드가 차단되는지(effective level 로 판정)
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
