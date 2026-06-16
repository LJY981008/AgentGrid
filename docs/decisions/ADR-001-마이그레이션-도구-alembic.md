# ADR-001: M1 스키마 마이그레이션 도구 = alembic

- **날짜**: 2026-06-16
- **상태**: 승인
- **결정자**: 사용자 / Claude 협의

## 맥락 (Context)

M1(데이터 수집·저장)에서 PostgreSQL 18 운영 서빙 스키마(stock·daily_bar·financial·investor_trade·short_sale·rule_version·top_entry)를 도입한다. 첫 스키마 작업이라 마이그레이션 체계를 먼저 정해야 한다. 제약:

- 직접 DDL(`CREATE/ALTER/DROP`)은 `pre-bash-guard.sh` 가 위험 패턴으로 차단 → **마이그레이션 파일 전제**.
- 스키마가 PG18 고급 기능을 쓴다: RANGE 파티션(daily_bar 연도별)·BRIN 인덱스·ENUM(market)·CHECK 제약(OHLC 정합)·JSONB(top_entry.factors). 도구의 표현력이 중요.
- 사용자는 Spring 백엔드 전문 → Flyway/Liquibase 경험 보유.

## 결정 (Decision)

**alembic 을 채택한다.** 단 alembic autogenerate 는 위 PG18 고급 기능(파티션·BRIN·ENUM·CHECK·JSONB)을 완전히 못 잡으므로, 해당 DDL 은 `op.execute()` raw SQL 로 명시 작성한다(autogenerate 맹신 금지). up/down 양방향 마이그레이션·버전 그래프를 활용한다.

## 검토한 대안 (Alternatives)

| 대안 | 장점 | 단점 | 기각 사유 |
|---|---|---|---|
| **alembic** (채택) | Python/SQLAlchemy 생태계 표준, up/down 양방향, 버전 그래프, psycopg 연동 | autogenerate 가 파티션/BRIN/ENUM 한계 → raw SQL 보강 필요 | — |
| yoyo-migrations | 순수 SQL(Flyway 유사 — 사용자 친숙), 가벼움 | Python 객체 매핑 약함, PG18 고급기능 표현력에서 alembic 열위 | 사용자가 alembic 선택. SQLAlchemy 연동·생태계 우위 |
| raw SQL 직접 실행 | 단순 | pre-bash-guard 차단, 버전관리·롤백 부재 | 하네스가 물리 차단 |

## 결과 (Consequences)

- **얻는 것**: 버전 관리되는 스키마 진화(롤백 가능), psycopg/SQLAlchemy 와 일관된 Python 스택.
- **감수하는 것**: 파티션·BRIN·ENUM·CHECK·JSONB 는 `op.execute()` 수동 작성(autogenerate 출력 검수 필수). 런타임 의존성 추가(alembic+sqlalchemy+psycopg[binary]) — 본 ADR 승인 후 `pyproject.toml` 반영은 devops-engineer 와 조율, 버전은 추측 금지·pip 실측 고정(uv.lock 핀).
- **Parquet 는 마이그레이션 대상 아님**(파일 산출물) — 스키마 진화는 적재 코드+컬럼 추가로 처리.
- **재검토 트리거**: autogenerate 보강 비용이 과도하거나, 서빙 스키마를 SQLAlchemy ORM 없이 운영하기로 하면 yoyo(순수 SQL) 재검토.

## 관련

- [[plans/M1-데이터파이프라인]] §스키마 / [[plans/stock-1st_plan]] §8 M1 / 미해결 #4(시계열DB)
- 스코핑 근거: M1 스코핑 워크플로우(db-architect) — daily_bar RANGE 파티션·BRIN, financial PIT(`disclosed_at`) 설계
