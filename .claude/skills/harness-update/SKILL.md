---
name: harness-update
description: Procedure for keeping the AgentGrid Claude Code harness (CLAUDE.md, rules, skills, agents, hooks, drift mappings) synchronized with the evolving codebase. Use when adding new conventions, patterns, modules, agents, or when harness-drift-check blocks a session. Trigger phrases - 하네스 업데이트, 컨벤션 추가, 규칙 추가, 새 패턴 도입, 드리프트 매핑 추가, 하네스 점검.
argument-hint: "[변경-요약?]"
---

# /harness-update — 하네스 지속 업데이트 절차

> **이 프로젝트의 핵심 규약**: 코드가 진화하면 하네스도 같은 커밋에서 진화한다.
> 물리 강제: `.claude/hooks/harness-drift-check.sh` (Stop 훅) — 매핑된 코드 변경에 문서 갱신이 없으면 세션 종료를 막는다.

## 1. 변경 분류 → 배치 위치 결정

| 변경 종류 | 갱신 위치 | 비고 |
|---|---|---|
| 코딩 규칙·컨벤션 (경로 스코프) | `.claude/rules/{backend,frontend}-conventions.md` | `paths:` glob 자동 로드. 짧은 규칙은 전부 여기 |
| 절차·진단 매크로·다중 파일 지식 | `.claude/skills/<name>/SKILL.md` | 슬래시 커맨드 필요하거나 지원 파일 동반 시 |
| 역할 분리가 필요한 반복 분석 | `.claude/agents/<name>.md` | 같은 분석 2회 반복 후에만 생성. name 중복 금지(조용히 폐기됨) |
| 물리 강제 필요한 규칙 | `.claude/hooks/*.sh` + `settings.json` 등록 | "성공 조용, 실패 시끄럽게". 차단은 PreToolUse + exit 2 만 신뢰 |
| 정책·구조·인덱스 | `CLAUDE.md` (루트/backend/frontend) | 루트 200줄 이내 유지 — 길어지면 rules/skills 로 분리 |
| 아키텍처 결정 기록 | `docs/decisions/ADR-{n}-{제목}.md` | 왜 그렇게 했는지 |
| 구현 의도·플랜 백업·전후 비교 | `docs/work-history/{날짜}-{작업명}.md` + INDEX 행 | 플랜 승인 직후 전문 백업. src 변경 커밋에 엔트리 동반 (drift 강제) |

## 2. 갱신 체크리스트

- [ ] 해당 파일 갱신 (실측 코드 예시 기반 — 가짜 예시 금지)
- [ ] 루트 `CLAUDE.md` 인덱스(BLOCKING 표·Skills/Agents 인덱스) 동기화
- [ ] **`harness-drift-check.sh` 매핑 표에 신규 매핑 추가** — 새 코드 영역 ↔ 문서 대응이 생겼다면 필수
  - 형식: `'코드경로패턴@@문서1:문서2'` (grep -E 패턴 @@ 콜론 구분 대상)
  - 예: 새 Consumer 도입 시 `'backend/.*Consumer\.java@@.claude/rules/backend-conventions.md'`
- [ ] 훅 변경 시 회귀 테스트: `.claude/hooks/tests/run.sh` 실행 + 신규 케이스 추가 (exit code + stderr 단언)
- [ ] 에이전트 추가/변경 시: 세션 재시작해야 등록됨을 사용자에게 고지. `name` 중복 금지 (조용히 폐기됨)
- [ ] 커스텀 메트릭 추가 시: `infra/monitoring/grafana/dashboards/` 패널 동시 갱신 (모니터링 지속 업데이트)
- [ ] docs/decisions·research 신규 문서 시: `docs/HOME.md` MOC 에 링크 추가 (drift 강제)
- [ ] 구현 작업 시: `docs/work-history/` 엔트리 (의도/목적 → 계획/플랜 백업 → Before → After → 비교) + `INDEX.md` 행 — src 변경 커밋에 동반 필수 (drift 강제)

## 3. 주기 감사 (대규모 변경 후 또는 격주)

```
Agent(subagent_type="harness-auditor", prompt="하네스 전수 감사 — 문서·코드 정합성, 버전 신선도, 훅 동작, drift 매핑 누락 보고")
```

## 4. 성장 로드맵 (아직 미도입 — 시점 도달 시 이 스킬 갱신)

> 2026-06-12 tbbe-hub 대비 갭 분석으로 검증·확장된 표. "단계에 안 맞는 선제 도입"을 막는 장치이기도 함.

| 시점 (트리거) | 도입 항목 | 참고 |
|---|---|---|
| 백엔드 코드 누적 시 | Spotless + Checkstyle (정적분석 승격) + PostToolUse 포맷 훅 | `/home/code/project/claude-setting/guide/phase-f-static-analysis.md` |
| 분석 에이전트 활동 누적 + 산출물 포맷 계약 정의 시 | `recommend-agent-on-stop.sh` + `subagent-stop-check.sh` (SubagentStop 검증) **세트** | tbbe-hub `.claude/hooks/` 동명 |
| 첫 read-only 분석 에이전트 추가 시 | 에이전트 `model` 핀(저비용) + `skills` preload 세트 적용 | tbbe-hub agents (model: sonnet 핀 13종) |
| 같은 구조물 2회째 작성 시 (첫 Consumer 2번째 등) | `.claude/rules/checklists.md` — 첫 구현의 실측 파일 목록을 체크리스트로 승격 | tbbe-hub `.claude/rules/checklists.md` |
| 동일 지시문 3회+ 복붙하는 일괄 작업 발생 시 | `.claude/prompts/` 재사용 프롬프트 | tbbe-hub `.claude/prompts/` |
| 첫 통합 테스트 패턴 다양화 시 | CLAUDE.md "통합 테스트 선택 기준" 절 (로컬 vs CI 위임) | tbbe-hub CLAUDE.md L23-28 |
| 환경 종속 allow(원격 IP·자격증명·MCP) 첫 필요 시 | settings.local.json 분리 운용 (정책=settings.json / 환경=local) | tbbe-hub 패턴 — **local 은 gitignore 유지** |
| worktree 작업 첫 권한 프롬프트 시 | `permissions.additionalDirectories` 1줄 | tbbe-hub settings.json L16 |
| MVP 세로 슬라이스 1개 완성 시 | `docs/onboarding/` 2-3종 (아키텍처·DB) + Repository 쿼리 20개 시 QUERY_CATALOG | tbbe-hub `docs/onboarding/` |
| 운영(스테이징) 배포 + 첫 인시던트 시 | 운영 진단 slash 매크로 (첫 장애 분석 명령을 매크로로 승격) | tbbe-hub `/prod-log`, `/dlq-check` 류 |
| 도메인 지식 누적 시 | 도메인 skills (flow-diagrams, status-lifecycle, scenarios 류) | tbbe-hub `.claude/skills/` |
| CI 안정화 후 | 주간 GC (schedule + 알림) | `claude-setting/guide/phase-h-weekly-gc.md` |

## 5. 참고 레퍼런스

- 하네스 규격 가이드: `/home/code/project/claude-setting/` (HARNESS_SETUP_GUIDE.md + guide/phase-*.md)
- 발전형 실전 적용: `/home/code/project/tbbe-hub/.claude/` (훅 10종·rules·skills·agents)
