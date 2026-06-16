---
name: feedback-migration-tooling
description: 스키마 변경은 마이그레이션 파일로만 — 직접 DDL 은 pre-bash-guard 가 차단. 도구는 alembic ADR 권고
metadata:
  type: feedback
---

스키마 변경은 반드시 마이그레이션 파일로만 처리한다. 직접 DDL(psql/docker exec 경유 포함) 실행 금지.

**Why:** `.claude/hooks/pre-bash-guard.sh` 가 `DROP (DATABASE|SCHEMA|TABLE)` / `TRUNCATE TABLE` / `TRUNCATE schema.` 패턴을 exit 2 로 물리 차단한다(실측 2026-06-16). CLAUDE.md 규약에도 "직접 DDL 은 pre-bash-guard 차단" 명시.

**How to apply:** 스키마 작업 시 마이그레이션 파일(up/down) 산출이 결과물. 마이그레이션 도구는 미정 — 2026-06-16 기준 `docs/decisions/` 에 ADR 없음, SQL/alembic 디렉토리 없음. Python 진영이므로 **alembic**(SQLAlchemy 코어 + autogenerate) 을 1순위로 ADR 제안. 단 PG18 파티션·BRIN 등은 autogenerate 한계 → raw SQL `op.execute()` 병용 전제. ADR 작성 전 도구 강행 금지(사용자 결정 지점). [[m1-storage-schema]]
