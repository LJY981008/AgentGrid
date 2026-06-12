# AGENTS.md

Codex/Gemini 등 코딩 에이전트용 진입 문서.

> ⚠️ **얇은 포인터 정책**: 이 파일에 규칙 본문을 복제하지 않는다 (tbbe-hub 의 AGENTS.md 드리프트 실패 사례 반면교사).
> 모든 규칙의 원본은 아래 파일들 — 충돌 시 원본이 우선.

## 필수 참조 (작업 전 읽기)

| 내용 | 원본 |
|---|---|
| 역할·작업 원칙·작업 완료 절차·구조 | [CLAUDE.md](CLAUDE.md) |
| 백엔드 컨벤션 (Java 21/Boot 4.1) | [.claude/rules/backend-conventions.md](.claude/rules/backend-conventions.md) |
| 로깅 규칙 | [.claude/rules/logging-rules.md](.claude/rules/logging-rules.md) |
| 프론트 컨벤션 (Next 16) + Next 동봉 규칙 | [.claude/rules/frontend-conventions.md](.claude/rules/frontend-conventions.md), [frontend/AGENTS.md](frontend/AGENTS.md) |
| 기획 현황 | [docs/plans/PLAN_STATUS.md](docs/plans/PLAN_STATUS.md) |

## 최소 불변 규칙 (훅이 없는 에이전트도 준수)

- 소통·문서·커밋 메시지는 한국어. 커밋 첫 줄 태그: `feat|fix|refactor|docs|test|chore|perf`
- 스키마 변경은 Flyway 마이그레이션 파일로만 (직접 DDL 금지)
- 추측 금지 — 코드/로그/문서 실측 후 진행. push 는 사용자 요청 시에만
- 검증: backend `cd backend && ./gradlew test --no-daemon` / frontend `cd frontend && npm run typecheck`
