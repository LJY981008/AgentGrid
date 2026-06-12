#!/usr/bin/env bash
# pre-bash-guard.sh — PreToolUse Bash 실행 전 위험 명령 차단 (AgentGrid)
# - exit 2 + stderr 메시지: 도구 실행 차단 + AI에 사유 반환
# - exit 0 + 무출력: 통과
# - 사용자 정책: git 관련 명령은 전부 허용 (force push 포함) — git 차단 규칙 없음
# - permissions.deny는 2026-06 실측 정상이나 환경별 무력화 보고가 잔존 → 본 훅을 1차 차단으로 유지 (defense-in-depth)
set -uo pipefail

if [[ "${CLAUDE_HOOKS_SKIP:-}" == "1" ]]; then
  exit 0
fi

INPUT=$(cat || true)
# 파싱 실패는 fail-open (다른 훅과 일관) — jq 에러 노출 방지
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null || echo "")
[[ -z "$CMD" ]] && exit 0

deny() {
  echo "[pre-bash-guard] 차단 사유: $1" >&2
  echo "명령: $CMD" >&2
  exit 2
}

# rm 재귀+강제 삭제 — 플래그 결합(-rf/-fr/-rfv)·분리(-r -f)·롱옵션(--recursive --force) 전부 커버
# 경계: 공백 + 셸 구분자(;&|) + 절대경로 prefix(/bin/rm). bash -c "..." 래핑 등은 정규식 한계로
# 본 가드가 못 잡음 — permissions 레이어와 이중 방어 전제 (단독 보안 경계 아님)
RM_SEG=""
[[ "$CMD" =~ (^|[[:space:]]|[\;\&\|\(])(/[^[:space:]]*/)?rm[[:space:]]+([^\|\;\&]*) ]] && RM_SEG="${BASH_REMATCH[3]}"
if [[ -n "$RM_SEG" ]]; then
  HAS_R=0; HAS_F=0
  { [[ "$RM_SEG" =~ (^|[[:space:]])--recursive([[:space:]]|$) ]] || [[ "$RM_SEG" =~ (^|[[:space:]])-[a-zA-Z]*[rR] ]]; } && HAS_R=1
  { [[ "$RM_SEG" =~ (^|[[:space:]])--force([[:space:]]|$) ]] || [[ "$RM_SEG" =~ (^|[[:space:]])-[a-zA-Z]*f ]]; } && HAS_F=1
  if [[ "$HAS_R" -eq 1 && "$HAS_F" -eq 1 ]]; then
    [[ "$RM_SEG" =~ (^|[[:space:]])/($|[[:space:]]) ]] && deny "rm -rf / (시스템 루트)"
    [[ "$RM_SEG" =~ (^|[[:space:]])/(bin|boot|dev|etc|home|lib|lib64|opt|proc|root|sbin|srv|sys|usr|var)($|[[:space:]]|/) ]] \
      && deny "rm -rf 시스템 디렉토리"
    [[ "$RM_SEG" =~ (^|[[:space:]])~ ]] && deny "rm -rf ~ (홈 디렉토리)"
    [[ "$RM_SEG" =~ (^|[[:space:]])\*($|[[:space:]]) ]] && deny "wildcard rm -rf *"
  fi
fi

# docker system/volume prune — 전체 데이터 삭제 위험
[[ "$CMD" =~ docker[[:space:]]+(system|volume)[[:space:]]+prune ]] && deny "docker prune 금지 (개별 rm 사용)"

# DDL / TRUNCATE 직접 실행 (psql/docker exec 경유 포함) — 대소문자 무관
# git commit 메시지 내 키워드는 실행 불가하므로 검사 제외 (오탐 방지)
SKIP_DDL=0
if [[ "$CMD" =~ git[[:space:]]+commit ]] && ! [[ "$CMD" =~ psql ]]; then
  SKIP_DDL=1
fi
if [[ "$SKIP_DDL" -eq 0 ]]; then
  shopt -s nocasematch
  [[ "$CMD" =~ (DROP[[:space:]]+(DATABASE|SCHEMA)|TRUNCATE[[:space:]]+TABLE|TRUNCATE[[:space:]]+[a-zA-Z_]+\.) ]] \
    && deny "DDL(DROP DATABASE/SCHEMA)/TRUNCATE 직접 실행 금지 (마이그레이션 파일로 처리)"
  shopt -u nocasematch
fi

exit 0
