#!/usr/bin/env bash
# pre-edit-guard.sh — PreToolUse Edit|Write|MultiEdit 가드 (AgentGrid)
#
# 목적: Read 없이 추측성 Edit 차단 (정확성 우선 원칙의 물리 강제)
#
# 로직 (lenient 모드):
#   1. tool_input.file_path 추출
#   2. file 존재 안 함 (Write 신규 파일) → 통과
#   3. 현재 세션 transcript 에서 동일 file_path 의 Read/Write/Edit tool_use 검색
#   4. 발견 → 통과 / 미발견 → exit 2 차단
#
# 우회:
#   - CLAUDE_HOOKS_SKIP=1 환경변수
#   - transcript_path 누락/읽기 실패 → fail-open (통과, 차단 안 함)

set -uo pipefail

if [[ "${CLAUDE_HOOKS_SKIP:-}" == "1" ]]; then
  exit 0
fi

INPUT="$(cat || true)"

TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || true)"
FILE_PATH="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null || true)"
TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || true)"

# file_path 없음 (이상 케이스) → fail-open
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Write 신규 파일 (존재 안 함) → 통과
if [[ "$TOOL_NAME" == "Write" ]] && [[ ! -e "$FILE_PATH" ]]; then
  exit 0
fi

# transcript 없음 → fail-open
if [[ -z "$TRANSCRIPT" ]] || [[ ! -f "$TRANSCRIPT" ]]; then
  exit 0
fi

# transcript 에서 Read/Write/Edit/MultiEdit tool_use 검색 (동일 file_path)
# — 세션 내 Write 로 생성·Edit 로 수정한 파일은 내용 인지 상태이므로 Read 와 동급 인정 (오탐 차단 방지)
JQ_FILTER='
  select(.message.content != null)
  | .message.content[]?
  | select(.type == "tool_use"
      and (.name == "Read" or .name == "Write" or .name == "Edit" or .name == "MultiEdit")
      and .input.file_path == $fp)
  | "hit"
'
FOUND="$(jq -r --arg fp "$FILE_PATH" "$JQ_FILTER" "$TRANSCRIPT" 2>/dev/null | head -1)"

# 서브에이전트 오탐 방지: 훅이 부모 transcript_path 를 받는 경우가 있어
# 같은 세션 디렉토리의 agent-*.jsonl (서브에이전트 transcript) 도 검색
if [[ "$FOUND" != "hit" ]]; then
  TDIR="$(dirname "$TRANSCRIPT")"
  while IFS= read -r af; do
    [[ -f "$af" ]] || continue
    FOUND="$(jq -r --arg fp "$FILE_PATH" "$JQ_FILTER" "$af" 2>/dev/null | head -1)"
    [[ "$FOUND" == "hit" ]] && break
  done < <(grep -rlF "$FILE_PATH" "$TDIR" --include='agent-*.jsonl' 2>/dev/null | tail -10)
fi

if [[ "$FOUND" == "hit" ]]; then
  exit 0
fi

REASON="[pre-edit-guard] Read 기록 없이 ${TOOL_NAME} 시도 차단.
파일: ${FILE_PATH}
사유: 현재 세션 transcript 에서 해당 파일의 Read 기록이 없음. 추측성 편집 방지.
조치: Edit 전에 Read tool 로 대상 파일 본문을 먼저 확인하세요.
우회: 정당한 사유가 있으면 사용자 동의 후 CLAUDE_HOOKS_SKIP=1 환경변수로 재시도."

echo "$REASON" >&2
exit 2
