#!/usr/bin/env bash
# AgentGrid 훅 회귀 테스트 — 훅 수정 시 반드시 실행 + 케이스 추가
# 단언: exit code + (선택) stderr 포함 텍스트
cd "$(dirname "$0")/../../.." || exit 1
PASS=0; FAIL=0
STDERR_FILE="$(mktemp)"

t() { # t <설명> <기대코드> <실제코드> [stderr필수문자열]
  local ok=1
  [[ "$2" != "$3" ]] && ok=0
  if [[ -n "${4:-}" ]] && ! grep -qF "$4" "$STDERR_FILE" 2>/dev/null; then ok=0; fi
  if [[ "$ok" == "1" ]]; then PASS=$((PASS+1)); echo "OK   $1 (exit=$3)";
  else FAIL=$((FAIL+1)); echo "FAIL $1 (기대=$2 실제=$3 stderr필수='${4:-}')"; head -3 "$STDERR_FILE"; fi
}
g() { jq -n --arg c "$1" '{tool_input:{command:$c}}' | .claude/hooks/pre-bash-guard.sh >/dev/null 2>"$STDERR_FILE"; echo $?; }
c() { jq -n --arg c "$1" '{tool_input:{command:$c}}' | .claude/hooks/verify-commit-msg.sh >/dev/null 2>"$STDERR_FILE"; echo $?; }

# ---- pre-bash-guard ----
RM='rm -rf'
t "guard: true&&\$RM /etc"        2 "$(g "true&&$RM /etc")" "차단 사유"
t "guard: true;\$RM /etc"         2 "$(g "true;$RM /etc")"
t "guard: /bin/\$RM /etc"         2 "$(g "/bin/$RM /etc")"
t "guard: \$RM / (루트)"          2 "$(g "$RM /")"
t "guard: \$RM ~ (홈)"            2 "$(g "$RM ~")"
t "guard: \$RM /tmp/x && ls"      0 "$(g "$RM /tmp/x && ls")"
t "guard: echo hello"             0 "$(g "echo hello")"
t "guard: git push force (오픈)"  0 "$(g "git push --force origin main")"
DT='DROP TABLE tools'
t "guard: psql DROP TABLE"        2 "$(g "psql -c '$DT'")" "DDL"
t "guard: docker volume prune"    2 "$(g "docker volume prune -f")"
t "guard: malformed json (open)"  0 "$(printf 'not-json' | .claude/hooks/pre-bash-guard.sh >/dev/null 2>&1; echo $?)"

# ---- verify-commit-msg ----
t "commit: -am bad"               2 "$(c 'git commit -am "bad msg"')" "컨벤션"
t "commit: --message= bad"        2 "$(c 'git commit --message="bad msg"')"
t "commit: --message bad"         2 "$(c 'git commit --message "bad msg"')"
t "commit: -am good"              0 "$(c 'git commit -am "fix: 버그 수정"')"
t "commit: -m scoped good"        0 "$(c 'git commit -m "feat(api): x 추가"')"
t "commit: -m bad"                2 "$(c 'git commit -m "bad"')"
HD=$'git commit -m "$(cat <<\'EOF\'\nrefactor: 구조 개선\n\n상세 설명\nEOF\n)"'
t "commit: HEREDOC good"          0 "$(c "$HD")"
HDBAD=$'git commit -am "$(cat <<\'EOF\'\n나쁜 메시지\nEOF\n)"'
t "commit: HEREDOC -am bad"       2 "$(c "$HDBAD")"
t "commit: 비-commit 통과"        0 "$(c 'git status')"
t "commit: malformed json (open)" 0 "$(printf 'x' | .claude/hooks/verify-commit-msg.sh >/dev/null 2>&1; echo $?)"

# ---- pre-edit-guard (mock transcript) ----
PEG_DIR="$(mktemp -d)"
READ_FILE="$PEG_DIR/read.txt"; UNREAD_FILE="$PEG_DIR/unread.txt"; TRANSCRIPT="$PEG_DIR/transcript.jsonl"
echo x > "$READ_FILE"; echo x > "$UNREAD_FILE"
jq -nc --arg fp "$READ_FILE" '{message:{content:[{type:"tool_use",name:"Read",input:{file_path:$fp}}]}}' > "$TRANSCRIPT"
peg() { jq -n --arg tn "$1" --arg fp "$2" --arg tr "$3" '{tool_name:$tn, tool_input:{file_path:$fp}, transcript_path:$tr}' \
        | .claude/hooks/pre-edit-guard.sh >/dev/null 2>"$STDERR_FILE"; echo $?; }
t "peg: Read 기록 있는 Edit 통과"   0 "$(peg Edit "$READ_FILE" "$TRANSCRIPT")"
t "peg: Read 기록 없는 Edit 차단"   2 "$(peg Edit "$UNREAD_FILE" "$TRANSCRIPT")" "pre-edit-guard"
t "peg: Write 신규 파일 통과"       0 "$(peg Write "$PEG_DIR/new.txt" "$TRANSCRIPT")"
t "peg: transcript 없음 fail-open"  0 "$(peg Edit "$UNREAD_FILE" "/nonexistent.jsonl")"
t "peg: SKIP=1 우회"               0 "$(CLAUDE_HOOKS_SKIP=1 peg Edit "$UNREAD_FILE" "$TRANSCRIPT")"
rm -rf "$PEG_DIR"

# ---- Stop 훅 (관련 변경 없을 때 무해 통과) ----
t "post-work-check 통과"          0 "$(printf '{"stop_hook_active":false}' | .claude/hooks/post-work-check.sh >/dev/null 2>&1; echo $?)"
t "post-work-check 재귀 방지"     0 "$(printf '{"stop_hook_active":true}' | .claude/hooks/post-work-check.sh >/dev/null 2>&1; echo $?)"

# ---- harness-drift-check 매핑 패턴 단위 검증 ----
echo "compose.yaml" | grep -qE '(docker-)?compose.*\.ya?ml'; t "drift 패턴: compose.yaml 매칭" 0 "$?"
echo ".claude/agents/new-agent.md" | grep -qE '\.claude/agents/[a-z-]+\.md'; t "drift 패턴: 신규 agent 매칭" 0 "$?"
echo "backend/CLAUDE.md" | grep -qxF "CLAUDE.md"; t "drift 대상: 정확 매칭(-x)이 부분매칭 거부" 1 "$?"

# ---- session-start / log-loaded-instructions ----
echo '{}' | .claude/hooks/session-start.sh | jq -e '.hookSpecificOutput.reloadSkills == true' >/dev/null; t "session-start JSON 유효" 0 "$?"
printf '{"files":["CLAUDE.md"]}' | .claude/hooks/log-loaded-instructions.sh; t "log-loaded-instructions 무해" 0 "$?"

rm -f "$STDERR_FILE"
echo "----"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
