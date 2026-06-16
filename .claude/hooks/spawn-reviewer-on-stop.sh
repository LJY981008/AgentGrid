#!/usr/bin/env bash
# Stop hook: git diff HEAD가 30줄 이상이면 code-reviewer 에이전트 호출 유도. (AgentGrid)
#   - Hook은 Agent를 직접 스폰할 수 없음 — decision:block reason에 호출 지시문 주입
#   - "생성자/검증자 분리" 원칙의 유도 수준 구현 (진짜 강제는 LLM 판단에 달림)
# stdin: JSON (stop_hook_active, ...)

set -euo pipefail

if [[ "${CLAUDE_HOOKS_SKIP:-}" == "1" ]]; then
  exit 0
fi

INPUT="$(cat || true)"

STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo "false")"
if [[ "$STOP_ACTIVE" == "true" ]]; then
  exit 0
fi

PROJECT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT" || exit 0

# 노이즈 경로 제외 — 세션상태/문서/락파일/생성물은 코드 리뷰 대상 아님
EXCLUDES=(':(exclude).omc' ':(exclude)docs' ':(exclude)*.csv' ':(exclude)*.log'
  ':(exclude).claude/hooks/.state' ':(exclude)__pycache__' ':(exclude)*.parquet'
  ':(exclude)*.svg')

STATS="$(git -C "$PROJECT" diff --stat HEAD -- "${EXCLUDES[@]}" 2>/dev/null | tail -1 || true)"
INS="$(echo "$STATS" | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+' | head -1 || echo 0)"
DEL="$(echo "$STATS" | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+' | head -1 || echo 0)"
LINES=$(( ${INS:-0} + ${DEL:-0} ))

# 30줄 미만이면 조용히 통과
if [[ "${LINES:-0}" -lt 30 ]]; then
  exit 0
fi

# 동일 diff 재발화 억제 — 마지막 리뷰 유도 시점의 diff 해시 기록
STATE_DIR="$PROJECT/.claude/hooks/.state"
mkdir -p "$STATE_DIR" 2>/dev/null || true
HASH_FILE="$STATE_DIR/last-review-diff.sha"
DIFF_HASH="$(git -C "$PROJECT" diff HEAD -- "${EXCLUDES[@]}" 2>/dev/null | sha1sum | cut -d' ' -f1 || true)"
if [[ -n "$DIFF_HASH" && -f "$HASH_FILE" ]] && [[ "$(cat "$HASH_FILE" 2>/dev/null)" == "$DIFF_HASH" ]]; then
  exit 0
fi
[[ -n "$DIFF_HASH" ]] && printf '%s' "$DIFF_HASH" > "$HASH_FILE" 2>/dev/null || true

jq -n --arg n "$LINES" '{
  decision: "block",
  reason: ("변경 " + $n + "줄 감지(노이즈 경로 제외). superpowers:code-reviewer 에이전트로 diff 리뷰 권장.\n호출: Agent(subagent_type=\"superpowers:code-reviewer\", prompt=\"git diff HEAD 검토 — 우선순위별 지적사항 보고\")\n생략하려면 다음 Turn에서 바로 세션 종료.")
}'
exit 0
