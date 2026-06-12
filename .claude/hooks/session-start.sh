#!/usr/bin/env bash
# SessionStart hook — 하네스 자기진화 규약 지원 (AgentGrid)
#   - reloadSkills: 세션 시작 시 스킬/커맨드 디렉토리 재스캔 (스킬 편집 직후 세션도 최신 보장)
#   - watchPaths: 하네스 핵심 파일 FileChanged 감시 (settings/rules/빌드설정/기획안 변경 인지)
#   - 성공 조용: JSON 한 줄 외 무출력

set -uo pipefail

PROJECT="${CLAUDE_PROJECT_DIR:-$(pwd)}"

jq -n --arg p "$PROJECT" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    reloadSkills: true,
    watchPaths: [
      ($p + "/.claude/settings.json"),
      ($p + "/.claude/rules"),
      ($p + "/backend/build.gradle"),
      ($p + "/frontend/package.json"),
      ($p + "/docs/plans")
    ]
  }
}'
exit 0
