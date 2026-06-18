"""create core tables (stock, ticker_history, daily_bar)

Revision ID: 0001
Revises:
Create Date: 2026-06-18

S5-a 첫 마이그레이션(ADR-006). PG18 코어 3테이블. raw SQL(op.execute) — 파티션·ENUM·CHECK·BRIN.
- stock: surrogate BIGINT PK + cik nullable UNIQUE(repo가 ""→NULL 매핑·생존편향). DELETE 금지(델=delisted_at).
- ticker_history: 시점별 ticker↔cik(valid_from<=t<valid_to). 구간중첩 EXCLUDE 제약은 S5-d(실 history) 동반
  — S5-b 는 floor→NULL 무한스냅샷 1행이라 지금 EXCLUDE 추가 시 S5-d 실구간과 겹쳐 거부(C2 재이연).
- daily_bar: 연도 RANGE 파티션·NUMERIC scale=storage.py(가격38,10·adj38,12) 일치·CHECK=DuckDB 게이트 동형(PG 2차 방어선)·FK 없음(D2). 빈 테이블(채움은 S5-b/c).
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# daily_bar 연도 RANGE 파티션 범위(EODHD 폐지 ~2000·비폐지 ~30년+ 수용). 범위 밖은 DEFAULT 파티션.
_PARTITION_START_YEAR = 1995
_PARTITION_END_YEAR = 2026


def upgrade() -> None:
    op.execute(
        "CREATE TYPE exchange_enum AS ENUM "
        "('NYSE','NASDAQ','NYSE_AMERICAN','NYSE_ARCA','BATS','OTC')"
    )
    op.execute(
        """
        CREATE TABLE stock (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            cik TEXT,
            ticker TEXT NOT NULL,
            name TEXT,
            exchange exchange_enum NOT NULL,
            listed_at DATE,
            delisted_at DATE,
            delisted_at_source TEXT,
            source TEXT NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    # 부분 UNIQUE — cik 있을 때만 유일성 강제(repo가 ""→NULL 매핑하므로 미해소 다수 NULL 공존).
    op.execute("CREATE UNIQUE INDEX stock_cik_uq ON stock (cik) WHERE cik IS NOT NULL")
    op.execute("CREATE INDEX stock_ticker_idx ON stock (ticker)")

    op.execute(
        """
        CREATE TABLE ticker_history (
            stock_id BIGINT NOT NULL REFERENCES stock(id),
            ticker TEXT NOT NULL,
            cik TEXT,
            valid_from DATE NOT NULL,
            valid_to DATE,
            PRIMARY KEY (stock_id, ticker, valid_from)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE daily_bar (
            ticker TEXT NOT NULL,
            trade_date DATE NOT NULL,
            open NUMERIC(38,10) NOT NULL,
            high NUMERIC(38,10) NOT NULL,
            low NUMERIC(38,10) NOT NULL,
            close NUMERIC(38,10) NOT NULL,
            volume BIGINT NOT NULL,
            value BIGINT,
            adj_factor NUMERIC(38,12) NOT NULL,
            source TEXT NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (ticker, trade_date),
            CONSTRAINT daily_bar_positive_price
                CHECK (open > 0 AND high > 0 AND low > 0 AND close > 0),
            CONSTRAINT daily_bar_ohlc
                CHECK (high >= low AND high >= open AND high >= close
                       AND low <= open AND low <= close),
            CONSTRAINT daily_bar_adj_positive CHECK (adj_factor > 0)
        ) PARTITION BY RANGE (trade_date)
        """
    )
    # 연도별 파티션 — 겹침 없음. 범위 밖(미래·아주 과거)은 DEFAULT 안전망.
    for year in range(_PARTITION_START_YEAR, _PARTITION_END_YEAR + 1):
        op.execute(
            f"CREATE TABLE daily_bar_{year} PARTITION OF daily_bar "
            f"FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')"
        )
    op.execute("CREATE TABLE daily_bar_default PARTITION OF daily_bar DEFAULT")
    op.execute("CREATE INDEX daily_bar_trade_date_brin ON daily_bar USING BRIN (trade_date)")


def downgrade() -> None:
    # FK·파티션 역순. daily_bar(파티션 CASCADE)·ticker_history(stock FK)·stock·ENUM.
    op.execute("DROP TABLE IF EXISTS daily_bar CASCADE")
    op.execute("DROP TABLE IF EXISTS ticker_history")
    op.execute("DROP TABLE IF EXISTS stock CASCADE")
    op.execute("DROP TYPE IF EXISTS exchange_enum")
