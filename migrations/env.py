"""alembic 환경 — compose DATABASE_URL 에서 PG 접속(psycopg3). raw SQL 마이그레이션.

⚠️ sqlalchemy.url 은 alembic.ini 에 하드코딩하지 않고 여기서 DATABASE_URL env 로 주입한다
(패스워드 비노출·환경별 분리). `postgresql://` → `postgresql+psycopg://` 치환으로 psycopg3
드라이버를 명시한다(SQLAlchemy 기본은 psycopg2). ORM 모델 없음(target_metadata=None) — PG18 기능
(파티션·ENUM·CHECK·BRIN)은 마이그레이션의 raw SQL(op.execute)로 다룬다(autogenerate 미사용).
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

_raw_url = os.environ.get("DATABASE_URL", "")
if not _raw_url:
    msg = "환경변수 DATABASE_URL 미설정 — alembic 은 compose 의 PG 접속 URL 이 필요합니다."
    raise RuntimeError(msg)
# psycopg3 드라이버 명시(SQLAlchemy 기본 postgresql:// 는 psycopg2 를 찾음).
_url = _raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", _url)

target_metadata = None


def run_migrations_offline() -> None:
    """오프라인(SQL 출력) 모드 — 연결 없이 URL 만으로 SQL 생성."""
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """온라인 모드 — 실제 PG 연결로 마이그레이션 실행."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
