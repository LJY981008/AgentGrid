#!/usr/bin/env bash
# PreToolUse hook: enforce conventional commit tag on `git commit -m`. (AgentGrid)
# stdin: JSON with tool_input.command
# stdout: JSON with hookSpecificOutput.permissionDecision

set -euo pipefail

if [[ "${CLAUDE_HOOKS_SKIP:-}" == "1" ]]; then
  exit 0
fi

INPUT="$(cat)"
CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""')"

# Only act on real `git commit` invocations
if ! printf '%s' "$CMD" | grep -qE '(^|[[:space:];&|])git[[:space:]]+commit([[:space:]]|$)'; then
  exit 0
fi

# Extract the first -m argument.
# Priority 1: HEREDOC form `-m "$(cat <<'DELIM' ... DELIM)"` — extract the heredoc body.
# Priority 2: quoted `-m "..."` or `-m '...'` (multi-line via slurp).
# Priority 3: unquoted `-m word`.
MSG="$(printf '%s' "$CMD" | perl -0777 -ne '
  if (/-m\s+"?\$\(\s*cat\s*<<\s*["'\'']?(\w+)["'\'']?\s*\n(.*?)\n\1/s) { print $2; exit }
  if (/(?:^|\s)-m\s+(?:"((?:\\.|[^"\\])*)"|'\''((?:\\.|[^'\''\\])*)'\''|(\S+))/s) { print ($1 // $2 // $3); exit }
')"

# No -m? Likely editor/HEREDOC commit — skip (can't check reliably)
if [[ -z "$MSG" ]]; then
  exit 0
fi

FIRST_LINE="${MSG%%$'\n'*}"

if printf '%s' "$FIRST_LINE" | grep -qE '^(feat|fix|refactor|docs|test|chore|perf)(\([^)]+\))?:[[:space:]]+'; then
  exit 0
fi

REASON="커밋 메시지 첫 줄이 컨벤션에 맞지 않습니다. 허용 태그: feat|fix|refactor|docs|test|chore|perf. 예: 'feat: add X'. 받은 메시지: '${FIRST_LINE}'"

# permissionDecision:deny → Claude에 피드백 주입 (논리적 차단)
jq -n --arg r "$REASON" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: $r
  }
}'

# exit 2 + stderr → 물리 차단 레이어 (deny JSON만으로는 차단력 부족 #45511)
echo "$REASON" >&2
exit 2
