"""실행 진입점 — `python -m stockpick.api`.

uvicorn 으로 0.0.0.0:8000 바인드(컨테이너 내부). 호스트 localhost 노출(127.0.0.1:8000)·포트 매핑은
compose 책임(후속 devops). env STOCKPICK_API_PORT 로 포트 조정 가능(기본 8000).

진입점이므로 print 허용(사용자 출력). 로깅 가드(configure_logging)는 app.create_app() startup 에서
이미 1회 호출된다.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    port = int(os.environ.get("STOCKPICK_API_PORT", "8000"))
    uvicorn.run("stockpick.api:app", host="0.0.0.0", port=port)  # noqa: S104 — 컨테이너 내부 바인드


if __name__ == "__main__":
    main()
