#!/usr/bin/env bash
#
# InstructionsLoaded 훅 — 로드된 CLAUDE.md·rules·skills 디버깅 로그 (AgentGrid)
# paths-glob 스코프 rules 가 실제 세션에 로드되는지 관측 — "규칙이 조용히 안 실리는" 드리프트 감지용.
#
# 운영 원칙:
# - 성공 조용: 항상 exit 0, stdout 무출력
# - 로그는 .state/ 누적 (gitignore). 10MB 초과 시 자동 rotate (.log → .log.1)

set -uo pipefail

STATE_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}/.claude/hooks/.state"
LOG="$STATE_DIR/instructions-loaded.log"
mkdir -p "$STATE_DIR"

if [[ -f "$LOG" ]] && [[ $(stat -c%s "$LOG" 2>/dev/null || echo 0) -gt 10485760 ]]; then
  mv -f "$LOG" "$LOG.1"
fi

INPUT="$(cat || true)"

{
  printf '=== %s session=%s ===\n' "$(date -Iseconds)" "${CLAUDE_SESSION_ID:-unknown}"
  printf '%s\n\n' "$INPUT"
} >> "$LOG" 2>/dev/null || true

exit 0
