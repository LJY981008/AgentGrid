#!/usr/bin/env bash
# PostToolUse(ExitPlanMode) — 플랜 승인 직후 work-history 백업 리마인더 (AgentGrid)
#   - 비차단(additionalContext 주입): 승인된 플랜 전문을 docs/work-history/ 로 백업 후 구현 시작 유도
#   - 물리 강제는 harness-drift-check 가 담당 (src 변경 + work-history 부재 시 세션 종료 차단)
#   - 성공 조용 원칙 대상 아님 — 이 훅 자체가 "알림"이 목적

set -uo pipefail

if [[ "${CLAUDE_HOOKS_SKIP:-}" == "1" ]]; then
  exit 0
fi

cat >/dev/null || true

jq -n '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: "[work-history 규약] 플랜이 승인되어 구현을 시작한다면 첫 행동: 승인된 플랜 전문을 docs/work-history/{YYYY-MM-DD}-{작업명}.md 로 백업 (템플릿 docs/templates/work-history-template.md — 의도/목적 + Before 실측 포함, INDEX.md 행 추가). 완료 시 After/비교를 채워 같은 커밋에 포함. src 변경 커밋에 엔트리가 없으면 drift 훅이 차단함."
  }
}'
exit 0
