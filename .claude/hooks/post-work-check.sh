#!/usr/bin/env bash
# Stop hook: 변경 스택만 한정해 빌드 검증 (AgentGrid 듀얼스택)
#   - backend/**/*.java 변경 → cd backend && ./gradlew compileJava compileTestJava
#   - frontend/src/** 변경 → npm run typecheck (package.json 에 스크립트 있을 때만)
#   - 해당 스택이 아직 빌드 불가(스캐폴딩 전)면 조용히 통과 — 프로젝트 성장에 맞춰 자동 활성화
#   - CLAUDE_HOOK_TEST=1 환경변수 있을 때만 백엔드 :test 추가 (opt-in)
#   - 실패 시 요약 20줄 stderr + exit 2 (asyncRewake 호환). 성공 시 무출력 exit 0.
# stdin: JSON (stop_hook_active, cwd, ...)

set -uo pipefail

if [[ "${CLAUDE_HOOKS_SKIP:-}" == "1" ]]; then
  exit 0
fi

INPUT="$(cat || true)"

# 재귀 방지
STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo "false")"
if [[ "$STOP_ACTIVE" == "true" ]]; then
  exit 0
fi

CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // ""' 2>/dev/null || true)"
PROJECT="${CLAUDE_PROJECT_DIR:-${CWD:-$(pwd)}}"
cd "$PROJECT" || exit 0

# porcelain XY+공백 3글자 제거 + rename(old -> new)은 new 경로만 — 공백 경로/rename 오파싱 방지
CHANGED="$(git -C "$PROJECT" status --porcelain 2>/dev/null | cut -c4- | sed 's/.* -> //' || true)"
[[ -z "$CHANGED" ]] && exit 0

fail() {
  local log="$1" label="$2"
  local summary
  summary="$(grep -E '^(FAILED|> Task|.* FAILED|Caused by|error TS[0-9]+|ERROR)' "$log" 2>/dev/null | head -20 || true)"
  [[ -z "$summary" ]] && summary="$(tail -n 20 "$log")"
  {
    echo "[post-work-check] ${label} 검증 실패. 수정 후 재시도 필요."
    echo "요약:"
    echo "$summary"
    echo ""
    echo "원본 로그: $log"
  } >&2
  exit 2
}

# ---- backend: Java 변경 시 Gradle 컴파일 ----
if echo "$CHANGED" | grep -qE '^backend/.*\.java$'; then
  if [[ -x "$PROJECT/backend/gradlew" ]]; then
    TASKS="compileJava compileTestJava"
    [[ "${CLAUDE_HOOK_TEST:-0}" == "1" ]] && TASKS="$TASKS test"
    LOG="/tmp/agentgrid-backend-check.log"
    echo "[post-work-check] backend 변경 감지 — gradle $TASKS" >&2
    # shellcheck disable=SC2086
    ( cd "$PROJECT/backend" && ./gradlew $TASKS --no-daemon -q ) > "$LOG" 2>&1 || fail "$LOG" "backend"
  fi
fi

# ---- frontend: src 변경 시 typecheck ----
if echo "$CHANGED" | grep -qE '^frontend/(src/|package\.json|tsconfig)'; then
  if [[ -f "$PROJECT/frontend/package.json" ]] \
     && jq -e '.scripts.typecheck' "$PROJECT/frontend/package.json" >/dev/null 2>&1 \
     && [[ -d "$PROJECT/frontend/node_modules" ]]; then
    LOG="/tmp/agentgrid-frontend-check.log"
    echo "[post-work-check] frontend 변경 감지 — npm run typecheck" >&2
    ( cd "$PROJECT/frontend" && npm run -s typecheck ) > "$LOG" 2>&1 || fail "$LOG" "frontend"
  fi
fi

exit 0
