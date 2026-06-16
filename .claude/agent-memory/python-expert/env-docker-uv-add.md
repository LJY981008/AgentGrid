---
name: env-docker-uv-add
description: 컨테이너에서 uv add 가 권한 거부되는 마운트 소유 불일치 함정과 검증된 우회 절차
metadata:
  type: project
---

`docker compose exec -T app uv add <pkg>` 가 **권한 거부**(`Permission denied`)로 실패한다.

**Why:** compose.yaml 이 `pyproject.toml` 만 바인드 마운트(호스트 uid 1000=code 소유)하고
`uv.lock` 은 마운트하지 않음 → uv.lock 은 이미지 내 COPY 본(컨테이너 uid 999=app 소유). 컨테이너
기본 유저(app)는 마운트된 호스트 pyproject 에 못 쓰고, 호스트 uid 로 실행하면 이미지내 uv.lock 에
못 쓴다. 어느 단일 uid 로도 둘 다 못 씀(소유자 갈림). 추가로 호스트엔 uv 바이너리 없음.

**How to apply:** 의존성 추가 시 검증된 절차(2026-06-16 실측):
```
docker compose run --rm --no-deps --user 1000:1000 -e UV_CACHE_DIR=/tmp/uvcache \
  -v "$PWD/uv.lock:/app/uv.lock" app uv add --no-sync <pkg>   # 호스트 pyproject+uv.lock 갱신
docker compose build app && docker compose up -d --no-deps app  # .venv 에 설치 반영(재생성)
```
- `--no-deps`: postgres 안 띄움(호스트 5432 선점 시 포트 충돌 회피).
- `--user 1000:1000`: 호스트 소유와 일치(둘 다 1000 으로 만들려고 uv.lock 도 -v 로 일시 마운트).
- `UV_CACHE_DIR=/tmp`: uid 1000 은 컨테이너 홈(/.cache) 못 씀.
- `--no-sync`: lock/pyproject 파일만 갱신(이미지 .venv 는 build 로 반영).
- 검증/format 쓰기도 컨테이너 app(999)→호스트 1000 소유 파일엔 못 씀 → `ruff format` 자동수정은
  호스트에서 Edit 도구로 직접 하고, `ruff check`/`mypy`/`pytest` 는 컨테이너 exec 로 읽기만.

**근본 해결(후속, devops-engineer):** compose 에 `./uv.lock:/app/uv.lock` 바인드 추가하면 둘 다
호스트 소유로 정합 → `--user 1000` 만으로 uv add 가능. 재생성·CI 영향 점검 필요해 단독 결정 보류 중.
관련 [[impl-tiingo-adapter]].
