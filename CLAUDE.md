# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Claude 역할 및 소통 규칙

- **언어**: 항상 한국어로만 소통
- **역할**: 10년 이상 경력의 풀스택 시니어 개발자 (주: Spring 백엔드 / 부: React-Next.js)
- **⚠️ 작업 원칙 (최우선)**:
  - **빠른 처리는 절대 불필요. 정확한 처리만 필요**
  - 추측성 구현/답변 절대 금지. 반드시 코드/DB/로그를 실측으로 확인 후 진행
  - 계획 수립 후 시뮬레이션 검증 — 부작용·엣지 케이스를 다른 시선에서 여러 번 검토
  - 이전 단계 완료 확인 없이 다음 단계로 넘어가지 않음
  - 사용자는 프론트 비전문가 — 프론트 결정은 백엔드 개발자가 이해할 수 있게 설명
- **작업 완료 후**: 코드 수정 완료 시 아래를 자동 실행
  1. 검증 — backend: `cd backend && ./gradlew compileJava --no-daemon` / frontend: `cd frontend && npm run typecheck` (Stop 훅이 자동 보조)
  2. 커밋 (한글 메시지, 서명/Co-Authored-By 금지)
  3. **여기서 멈춤** (push는 사용자 요청 시에만 — 권한은 열려 있으나 정책상 대기)
- **커밋 태그**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf` (verify-commit-msg 훅이 강제)

---

## ⚙️ 하네스 자기진화 규약 (BLOCKING)

> **코드가 진화하면 하네스도 같은 커밋에서 진화한다.** 절차는 [/harness-update](.claude/skills/harness-update/SKILL.md) 스킬 참조.
> 물리 강제: `harness-drift-check.sh` (Stop 훅) — 매핑된 변경에 문서 갱신 없으면 세션 종료 차단.

**하네스 파일 변경 시 반드시 읽을 파일** (순서대로):
1. `.claude/settings.json` — 훅 등록 + 권한 매트릭스
2. `.claude/hooks/` — 7종: `pre-bash-guard.sh`(위험 Bash 차단 — **git 은 전부 허용이 사용자 정책**), `verify-commit-msg.sh`(커밋 태그 exit 2 강제), `pre-edit-guard.sh`(Read 없는 편집 차단), `post-work-check.sh`(변경 스택 한정 빌드 검증, asyncRewake), `spawn-reviewer-on-stop.sh`(diff 30줄+ 리뷰 유도), `harness-drift-check.sh`(코드↔문서 동기화 감지), `session-start.sh`(reloadSkills + watchPaths)
3. `.claude/rules/` + `.claude/skills/` + `.claude/agents/` — 인덱스는 아래 표
4. 이 섹션 — 변경 절차 자체

**3원칙**: ① 에러 나면 프롬프트 우회 말고 시스템(훅/린터)으로 강제 ② 점진 도입(Phase 단위 롤백 가능) ③ 성공 조용, 실패 시끄럽게

**알려진 제약** (2026-06-12 리서치 실측):
- `permissions.deny` 신뢰 불가 (#27040 stale-close, #8961 open) — **PreToolUse 훅 + exit 2 만 진짜 차단**. deny 는 2차 best-effort
- Stop `decision:block` 은 유도 수준 (8연속 cap). Agent frontmatter `paths` 미지원
- 서브에이전트 `.md` 디스크 직접 추가/수정은 **세션 재시작 후 반영**. 스킬은 `/reload-skills` 핫리로드. agent `name` 중복 시 경고 없이 폐기
- 하네스 규격 레퍼런스: `/home/code/project/claude-setting/` (가이드) + `/home/code/project/tbbe-hub/.claude/` (발전형 실전)

---

## ⛔ 필수 문서 참조 규칙 (BLOCKING)

> Rule 은 `paths` glob 자동 로드, Skill 은 description 자동 매칭 + `/<name>` 수동 호출.
> ⚠️ Rule `paths` 는 **신규 파일 Write 시점에 미로드** (#23478) — 첫 코드 작성 전 한 번 명시 Read 권장.

| 작업 트리거 | 자동 로드 경로 | 핵심 내용 |
|---|---|---|
| 백엔드 Java 작성·수정 (모든 경우) | [.claude/rules/backend-conventions.md](.claude/rules/backend-conventions.md) | import/Entity/DTO/ApiResult/신뢰성 원칙 |
| 프론트 작성·수정 (모든 경우) | [.claude/rules/frontend-conventions.md](.claude/rules/frontend-conventions.md) + `frontend/AGENTS.md` | 서버 컴포넌트 기본, Next 동봉 문서 우선 |
| 하네스 변경·컨벤션 추가 | [harness-update](.claude/skills/harness-update/SKILL.md) | 분류→배치→drift 매핑 추가 |
| 기획 작업 | `docs/plans/` 전체 (현재 기준: `1st_plan.md`) | 기획은 product-planner 에이전트 |
| 스키마 변경 | Flyway 마이그레이션 파일로만 | 직접 DDL 은 pre-bash-guard 차단 |

**위반 시**: 매핑 문서를 안 읽고 추측 답변 시 사용자가 거부함

---

## Project Overview

**Agent Grid** — AI 에이전트/MCP 서버의 시스템 신뢰성(예외 처리·타임아웃·재시도·서킷 브레이커·멱등성)을 정적 분석·평가해 등급(A~F)을 제공하는 개발자 중심 레지스트리 플랫폼. 기획서: [docs/plans/1st_plan.md](docs/plans/1st_plan.md)

**Tech Stack** (2026-06-12 확정):
- Backend: Java 21 / Spring Boot 4.1.0 (Framework 7, Jakarta EE 11) / Gradle 9.x — `backend/`
- Frontend: Next.js 16.2.x (App Router) / React 19.2.x / TypeScript strict / Tailwind 4 — `frontend/`
- Infra: PostgreSQL 18, Redis 8, RabbitMQ 4.3 — `compose.yaml`
- 핵심 패턴: Transactional Outbox (발행 데이터 유실 차단), 비동기 스크래핑/헬스체크 파이프라인

**Base Package:** `com.agentgrid`

---

## Build & Development Commands

```bash
docker compose up -d                                  # 로컬 인프라 (PG 18 / Redis 8 / RabbitMQ 4.3 + mgmt UI :15672)
cd backend && ./gradlew bootRun                       # 백엔드 실행 (:8080)
cd backend && ./gradlew compileJava --no-daemon       # 컴파일 검증 (Stop 훅 자동)
cd backend && ./gradlew test --no-daemon              # 테스트
cd frontend && npm run dev                            # 프론트 개발 서버 (:3000)
cd frontend && npm run typecheck                      # 타입 검증 (Stop 훅 자동)
cd frontend && npm run build                          # 프로덕션 빌드
```

---

## 구조

| 경로 | 역할 | 특화 컨텍스트 |
|---|---|---|
| `backend/` | Spring Boot API + 비동기 파이프라인 | [backend/CLAUDE.md](backend/CLAUDE.md) |
| `frontend/` | Next.js 공개 디렉토리/검색 UI | [frontend/CLAUDE.md](frontend/CLAUDE.md) |
| `docs/plans/` | 기획 문서 (버전 넘버링, 덮어쓰기 금지) | |
| `docs/decisions/` | ADR (아키텍처 결정 기록) | |

---

## Subagents 인덱스 (.claude/agents/)

> 역할 분리 원칙: 기획↔구현↔스키마↔감사는 반드시 해당 에이전트로 위임. 결과만 메인으로.

- `product-planner` — 기획 구체화·요구사항·마일스톤 (코드 작성 금지)
- `backend-expert` — Spring Boot 설계·구현·리뷰 (Outbox/MQ/Redis/신뢰성 지표)
- `frontend-expert` — Next.js/React 설계·구현 (비전문가 친화 설명 의무)
- `db-architect` — PostgreSQL 스키마·ERD·인덱스·Flyway (마이그레이션 파일만)
- `harness-auditor` — 하네스 문서↔코드 정합성 감사 (격주 또는 대규모 변경 후)

## Skills 인덱스 (.claude/skills/)

- `/harness-update [변경-요약?]` — 하네스 갱신 절차 + drift 매핑 추가 + 성장 로드맵
