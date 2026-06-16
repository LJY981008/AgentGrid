#!/usr/bin/env bash
# Stop hook: 변경 감지 시 Python 검증 (stockpick)
#   - src|tests 의 *.py 변경 → ruff check + mypy + pytest (도구 설치 시에만 — uv 환경 전 점진 활성)
#   - 도구 미설치 또는 변경 없으면 조용히 통과
#   - 실패 시 요약 20줄 stderr + exit 2 (asyncRewake 호환). 성공 무출력.
# stdin: JSON (stop_hook_active, cwd, ...)

set -uo pipefail

if [[ "${CLAUDE_HOOKS_SKIP:-}" == "1" ]]; then
  exit 0
fi

INPUT="$(cat || true)"
STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo "false")"
[[ "$STOP_ACTIVE" == "true" ]] && exit 0

CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null || true)"
PROJECT="${CLAUDE_PROJECT_DIR:-${CWD:-$(pwd)}}"
cd "$PROJECT" || exit 0

# porcelain XY+공백 3글자 제거 + rename 은 new 경로만
CHANGED="$(git -C "$PROJECT" status --porcelain 2>/dev/null | cut -c4- | sed 's/.* -> //' || true)"
[[ -z "$CHANGED" ]] && exit 0

echo "$CHANGED" | grep -qE '^(src|tests)/.*\.py$' || exit 0

# uv 환경 우선, 없으면 시스템 python (도구 없으면 각 단계 스킵)
RUN="python3 -m"
command -v uv >/dev/null 2>&1 && [[ -d "$PROJECT/.venv" ]] && RUN="uv run python -m"

fail() {
  { echo "[post-work-check] $1 실패. 수정 후 재시도 필요."; echo "요약:"; tail -n 20 "$2"; echo ""; echo "원본 로그: $2"; } >&2
  exit 2
}

LOG="/tmp/stockpick-check.log"
# ruff (린트) — 설치 시
if $RUN ruff --version >/dev/null 2>&1; then
  $RUN ruff check src tests > "$LOG" 2>&1 || fail "ruff" "$LOG"
fi
# mypy (타입) — 설치 시
if $RUN mypy --version >/dev/null 2>&1; then
  $RUN mypy > "$LOG" 2>&1 || fail "mypy" "$LOG"
fi
# pytest — 설치 시 (PYTHONPATH=src 로 src 레이아웃 로드)
if $RUN pytest --version >/dev/null 2>&1; then
  PYTHONPATH=src $RUN pytest -q > "$LOG" 2>&1 || fail "pytest" "$LOG"
fi

exit 0
