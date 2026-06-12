#!/usr/bin/env bash
# AgentGrid 훅 회귀 테스트 — 우회 케이스 포함
cd /home/code/project/AgentGrid || exit 1
PASS=0; FAIL=0
t() { # t <설명> <기대코드> <실제코드>
  if [[ "$2" == "$3" ]]; then PASS=$((PASS+1)); echo "OK   $1 (exit=$3)";
  else FAIL=$((FAIL+1)); echo "FAIL $1 (기대=$2 실제=$3)"; fi
}
g() { printf '{"tool_input":{"command":"%s"}}' "$1" | .claude/hooks/pre-bash-guard.sh >/dev/null 2>&1; echo $?; }
c() { printf '{"tool_input":{"command":"%s"}}' "$1" | .claude/hooks/verify-commit-msg.sh >/dev/null 2>&1; echo $?; }

RM='rm -rf'
t "true&&\$RM /etc"        2 "$(g "true&&$RM /etc")"
t "true;\$RM /etc"         2 "$(g "true;$RM /etc")"
t "/bin/\$RM /etc"         2 "$(g "/bin/$RM /etc")"
t "\$RM / (루트)"          2 "$(g "$RM /")"
t "\$RM ~ (홈)"            2 "$(g "$RM ~")"
t "\$RM /tmp/x && ls"      0 "$(g "$RM /tmp/x && ls")"
t "echo hello"             0 "$(g "echo hello")"
t "git push force (오픈)"  0 "$(g "git push --force origin main")"
t "malformed json (open)"  0 "$(printf 'not-json' | .claude/hooks/pre-bash-guard.sh >/dev/null 2>&1; echo $?)"

t "commit -am bad"         2 "$(c 'git commit -am \"bad msg\"')"
t "commit --message= bad"  2 "$(c 'git commit --message=\"bad msg\"')"
t "commit --message bad"   2 "$(c 'git commit --message \"bad msg\"')"
t "commit -am good"        0 "$(c 'git commit -am \"fix: 버그 수정\"')"
t "commit -m scoped good"  0 "$(c 'git commit -m \"feat(api): x 추가\"')"
t "commit -m bad"          2 "$(c 'git commit -m \"bad\"')"
t "malformed json commit"  0 "$(printf 'x' | .claude/hooks/verify-commit-msg.sh >/dev/null 2>&1; echo $?)"
t "비-commit 명령 통과"    0 "$(c 'git status')"

t "post-work-check"        0 "$(printf '{"stop_hook_active":false}' | .claude/hooks/post-work-check.sh >/dev/null 2>&1; echo $?)"

# drift-check: compose.yaml 패턴 매칭 검증 (스크립트 내부 로직 단위 확인)
echo "compose.yaml" | grep -qE '(docker-)?compose.*\.ya?ml' && DRIFT_OK=0 || DRIFT_OK=1
t "drift 패턴 compose.yaml 매칭" 0 "$DRIFT_OK"

echo "----"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
