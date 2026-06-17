# stockpick 개발/실행 이미지 — uv 기반 재현 가능 Python 환경
#
# 실측 근거(2026-06-16, docs.astral.sh/uv/guides/integration/docker):
#   - uv 0.11.21 (2026-06-11 릴리스) 를 distroless 이미지에서 COPY 로 주입 (latest 금지·버전 고정)
#   - 베이스는 python:3.12-slim-trixie (공식 권장 — uv 자체 이미지 대신 표준 python + uv 바이너리 주입)
#   - 2단계 sync: 의존성 레이어(--no-install-project) ↔ 소스 레이어 분리로 캐시 효율
#   - BuildKit cache mount(--mount=type=cache) 로 uv 다운로드 캐시 재사용
#   - UV_LINK_MODE=copy: 캐시 마운트와 .venv 가 다른 파일시스템이라 하드링크 불가 → 복사
#   - UV_COMPILE_BYTECODE=1: import 지연 제거(.pyc 사전 컴파일)
#   - UV_PYTHON_DOWNLOADS=0: 베이스 이미지의 시스템 파이썬 사용(uv 가 별도 파이썬 안 받음)
#
# ⚠️ 이 이미지는 dev 환경(ruff/mypy/pytest 포함) — UV_NO_DEV 안 씀.
#    런타임 의존성 = duckdb·fastapi·httpx·pyarrow·uvicorn[standard] (pyproject.toml [project].dependencies).
#    2단계 uv sync 로 의존성/소스 레이어 분리(단일 FROM 스테이지 — prod 분리는 운영 배포 시점에).

FROM python:3.12-slim-trixie

# uv 바이너리 주입 — 버전 고정(재현성). 갱신 시 이 태그와 CLAUDE.md 동기.
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

# uv 동작 환경변수 (위 주석 참조)
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    # .venv/bin 을 PATH 앞에 → `python`·`ruff`·`pytest` 가 가상환경 것을 가리킴(uv run 없이도 동작)
    PATH="/app/.venv/bin:$PATH" \
    # 컨테이너 표준 출력 버퍼링 해제(로그 즉시 노출)
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1단계 — 의존성만 설치(프로젝트 자체 제외). pyproject.toml·uv.lock 만 바인드 →
#   소스가 바뀌어도 이 레이어는 캐시 적중(의존성 미변경 시). README/소스 불필요(빌드 백엔드 미실행).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# 2단계 — 소스 복사 후 프로젝트 자체 설치(editable). 개발 시 ./src 바인드 마운트가
#   이 .pth(=/app/src) 위로 덮여도 경로 동일 → import 유지.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# non-root 실행 — /app(.venv 포함) 소유권 이전 후 전환.
#   바인드 마운트된 호스트 소스는 호스트 소유라 읽기는 되지만, .venv 쓰기·캐시 생성은 컨테이너 유저로.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app

# 기본 command: 상주(개발 컨테이너로 띄워두고 `docker compose exec app ...` 로 검증 실행).
#   API 서버 진입점 존재(`python -m stockpick.api`) — compose 가 command 로 오버라이드해 uvicorn:8000 상주.
#   기본 CMD 는 개발 상주용 sleep infinity 유지(exec 검증 편의).
CMD ["sleep", "infinity"]
