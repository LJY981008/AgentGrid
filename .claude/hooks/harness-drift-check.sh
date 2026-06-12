#!/usr/bin/env bash
# Stop hook: 코드/설정 변경 ↔ 하네스 문서 동기화 감지 (AgentGrid)
#   - git diff HEAD 의 변경 파일이 매핑 표의 문서와 연관되는데,
#     해당 문서가 같은 diff 에 없으면 decision:block 으로 동기화 유도
#   - "하네스 지속 업데이트" 요구의 물리 강제 레이어 — 프롬프트 의존 금지
#   - 매핑 표는 개발 진행에 따라 계속 추가한다 (/harness-update 스킬 참조)
#   - 동일 diff 재발화 억제: .state/harness-drift.sha
# stdin: JSON (stop_hook_active, ...)

set -uo pipefail

if [[ "${CLAUDE_HOOKS_SKIP:-}" == "1" ]]; then
  exit 0
fi

INPUT="$(cat || true)"
STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo "false")"
[[ "$STOP_ACTIVE" == "true" ]] && exit 0

PROJECT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT" || exit 0

# tracked 변경 + untracked 신규 파일(예: 새 agent/skill 추가) 합집합 — 신규 하네스 요소도 동기화 감지
CHANGED="$({ git -C "$PROJECT" diff --name-only HEAD -- ':(exclude).omc' ':(exclude).claude/hooks/.state' 2>/dev/null;
             git -C "$PROJECT" ls-files --others --exclude-standard 2>/dev/null; } | sort -u || true)"
[[ -z "$CHANGED" ]] && exit 0

# 매핑 표: 코드 경로 패턴 @@ 동기화 대상 문서 (콜론 구분 다중 — 하나라도 diff 에 있으면 충족)
# 구분자 @@ — 패턴 내 정규식 alternation(|) 과 충돌 방지. 패턴은 grep -E.
# ⚠️ 개발하며 추가할 것: Entity ↔ DB 스킬, Controller ↔ API 스펙, Consumer ↔ 플로우 문서 등
declare -a RULES=(
  '\.claude/agents/[a-z-]+\.md@@CLAUDE.md'
  '\.claude/skills/.*/SKILL\.md@@CLAUDE.md'
  '\.claude/rules/[a-z-]+\.md@@CLAUDE.md'
  '\.claude/settings\.json@@CLAUDE.md'
  '\.claude/hooks/[a-z-]+\.sh@@CLAUDE.md'
  'backend/build\.gradle@@backend/CLAUDE.md'
  'backend/settings\.gradle@@backend/CLAUDE.md'
  'backend/Dockerfile@@backend/CLAUDE.md'
  'backend/src/test/java/com/agentgrid/TestcontainersConfiguration\.java@@backend/CLAUDE.md'
  'frontend/package\.json@@frontend/CLAUDE.md'
  'frontend/Dockerfile@@frontend/CLAUDE.md'
  '(docker-)?compose.*\.ya?ml@@CLAUDE.md'
  'infra/monitoring/.*@@CLAUDE.md:backend/CLAUDE.md'
  'docs/plans/.*\.md@@docs/plans/PLAN_STATUS.md'
  'docs/(decisions|research)/.*\.md@@docs/HOME.md'
)

MISSING=""
for rule in "${RULES[@]}"; do
  PATTERN="${rule%%@@*}"
  DOCS="${rule#*@@}"
  if echo "$CHANGED" | grep -qE "$PATTERN"; then
    # 트리거 파일과 대상 문서가 동일 케이스 (예: CLAUDE.md 자기 자신) 면 충족 처리
    SYNCED=0
    IFS=':' read -ra DOC_ARR <<< "$DOCS"
    for doc in "${DOC_ARR[@]}"; do
      # -x 정확 라인 매칭 — "CLAUDE.md" 가 backend/CLAUDE.md 에 부분 매칭되는 오탐 방지
      if echo "$CHANGED" | grep -qxF "$doc"; then
        SYNCED=1
        break
      fi
    done
    if [[ "$SYNCED" -eq 0 ]]; then
      TRIGGER="$(echo "$CHANGED" | grep -E "$PATTERN" | head -2 | tr '\n' ' ')"
      MISSING="${MISSING}- ${TRIGGER}→ ${DOCS//:/ 또는 }\n"
    fi
  fi
done

[[ -z "$MISSING" ]] && exit 0

# 동일 diff 재발화 억제
STATE_DIR="$PROJECT/.claude/hooks/.state"
mkdir -p "$STATE_DIR" 2>/dev/null || true
HASH_FILE="$STATE_DIR/harness-drift.sha"
DIFF_HASH="$(printf '%s' "$CHANGED$MISSING" | sha1sum | cut -d' ' -f1 || true)"
if [[ -n "$DIFF_HASH" && -f "$HASH_FILE" ]] && [[ "$(cat "$HASH_FILE" 2>/dev/null)" == "$DIFF_HASH" ]]; then
  exit 0
fi
[[ -n "$DIFF_HASH" ]] && printf '%s' "$DIFF_HASH" > "$HASH_FILE" 2>/dev/null || true

jq -n --arg m "$(printf '%b' "$MISSING")" '{
  decision: "block",
  reason: ("하네스 문서 동기화 누락 감지 — 아래 변경에 대응하는 문서가 같은 diff 에 없음:\n" + $m + "\n해당 문서를 실측 기반으로 갱신하거나, 갱신 불필요 사유를 확인 후 다음 Turn 에서 세션 종료. (/harness-update 스킬 참조)")
}'
exit 0
