# B-env — Docker 기반 uv 개발/실행 환경

- **날짜**: 2026-06-16
- **유형**: 하네스/인프라
- **담당**: devops-engineer (메인 리뷰 후 커밋)

## 의도

"어디서 돌려도 동일하게 실행"(재현성 = `uv.lock` + 이미지 고정). 로컬에 uv 미설치 — uv 를 이미지 안에 넣는 게 핵심. 런타임 의존성은 아직 추가하지 않고(dev 도구만) 환경 골격 + lock 을 먼저 확립. 다음 단계(B-pipeline)에서 `uv add` 로 데이터 라이브러리 실측 고정.

## Before

- `compose.yaml`: postgres 단일 서비스(PG18).
- `pyproject.toml`: `dependencies=[]`, dev 도구는 `[project.optional-dependencies]`, description 이 한국 주식으로 stale.
- Dockerfile / .dockerignore / uv.lock **부재**.

## 실측 — uv Docker 패턴 (추측 금지)

출처: `docs.astral.sh/uv/guides/integration/docker` + `concepts/projects/dependencies` (2026-06-16 WebFetch).

- uv 최신 = **0.11.21** (2026-06-11 릴리스) → 태그 고정(latest 금지).
- 권장 패턴: `python:3.12-slim-trixie` + `COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/`(uv 자체 이미지 대신 표준 파이썬에 바이너리 주입).
- 2단계 sync: `uv sync --locked --no-install-project`(의존성 레이어, README/소스 불필요 — 빌드 백엔드 미실행) → `COPY . /app` → `uv sync --locked`(프로젝트 editable 설치).
- BuildKit `--mount=type=cache,target=/root/.cache/uv` + `--mount=type=bind`(lock/pyproject) 로 캐시 재사용.
- `UV_LINK_MODE=copy`(캐시·venv 파일시스템 분리), `UV_COMPILE_BYTECODE=1`, `UV_PYTHON_DOWNLOADS=0`(시스템 파이썬).
- non-root: 공식 가이드 미제공 → 직접 `groupadd/useradd app` + `chown` 후 `USER app`.

## 작성/수정 파일

| 파일 | 변경 |
|---|---|
| `Dockerfile` (신규) | 멀티스테이지 uv 패턴, non-root, 캐시 마운트, PATH=/app/.venv/bin |
| `.dockerignore` (신규) | .venv·캐시·.git·data·docs·.claude 등 빌드 컨텍스트 최소화 |
| `uv.lock` (신규) | 14패키지 고정(dev 도구 + 전이). 컨테이너 `uv lock` 으로 생성(로컬 uv 없음) |
| `compose.yaml` | `app` 서비스 추가(build·depends_on healthy·소스 바인드·DATABASE_URL). postgres **무변경** |
| `pyproject.toml` | description 미국 주식 교정 + dev 도구를 `[dependency-groups]`(PEP 735)로 이동 |
| `CLAUDE.md` | Build & Development 워크플로우 Docker화 + 구조 표에 Dockerfile/compose/uv.lock |

## After — 검증 출력 (실측)

```
uv --version                → uv 0.11.21 (x86_64-unknown-linux-musl)
docker compose config -q    → OK (version 필드 없음)
docker compose build app    → Built (성공)
python -c import stockpick  → /app/src/stockpick/__init__.py  (바인드 마운트 editable 정상)
ruff check src tests        → 1 finding: UP042 (types.py:15, 기존 코드 — 본 작업 무관)
mypy                        → Success: no issues found in 6 source files
pytest -q                   → 4 passed (계약 스모크 4/4)
```

### 빌드 캐시 효율 (소스만 변경 시뮬레이션)

```
COPY uv 바이너리            → CACHED
uv sync --no-install-project → CACHED   (의존성 레이어 적중)
uv sync --locked (프로젝트)  → 0.5s     (프로젝트만 재설치)
총 재빌드                    → ~4.0s
```

의존성/소스 레이어 분리가 의도대로 동작 — 소스 수정 시 의존성 레이어 캐시 유지.

## 회고 / 디버깅 (실측 후 수정)

1. **distroless uv 이미지로 `uv lock` 실패** — `ghcr.io/astral-sh/uv:0.11.21` 은 파이썬 없음 → libc 탐지 실패. `:python3.12-trixie-slim`(파이썬 번들)로 lock 생성. (entrypoint 가 이미 `uv` 라 `uv uv lock` 중복도 1차 오류였음.)
2. **dev 도구 미설치 (핵심 버그)** — 초기엔 `[project.optional-dependencies].dev` 였는데 `uv sync` 는 extra 를 기본 설치 안 함 → 컨테이너에 ruff/mypy/pytest 부재(`exec: not found`). 실측 확인 후 `[dependency-groups]`(PEP 735)로 이동 → `uv sync` 기본 설치 → 해결. lock 재생성·재빌드로 검증.
3. **호스트 5432 선점** — 별도 프로젝트 `aicrawl-postgres` 가 5432 점유 → `docker compose up -d`(postgres 포함) 충돌. 다른 프로젝트 컨테이너는 건드리지 않음. `docker compose up -d --no-deps app` 로 app 만 띄워 검증. 환경 이슈(설정 결함 아님) — CLAUDE.md 에 주의 명시.

## 미해결 / 다음 단계

- ruff **UP042**(types.py: `Market(str, Enum)` → `StrEnum` 권장): 도메인 계약 + 직렬화 시맨틱 영향 → B-contract/python-expert 가 테스트와 함께 판단. 인프라 작업에서 도메인 코드 무단 수정 금지로 미적용.
- prod 전용 멀티스테이지 분리(`--no-editable`·`--no-dev`·distroless 런타임)는 서버/CLI 진입점 생기는 B-pipeline 이후.
- `app` command 는 현재 `sleep infinity`(상주) — FastAPI/CLI 진입점 생기면 교체.
