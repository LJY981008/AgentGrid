"""stock.listing_status (active/delisted)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-18

S5-b — 종목마스터의 생존상태 플래그. EODHD 가 폐지일을 안 줘 delisted_at(date) 으로는 active/delisted
구분이 안 되므로, `listing_status`('active'|'delisted') 컬럼으로 표현(날짜는 S5-c 가 가격에서 backfill).
빈 테이블(S5-a 0001 은 스키마만)이라 DEFAULT 'active' 안전.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE stock ADD COLUMN listing_status TEXT NOT NULL DEFAULT 'active'")
    op.execute(
        "ALTER TABLE stock ADD CONSTRAINT stock_listing_status_chk "
        "CHECK (listing_status IN ('active', 'delisted'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stock DROP CONSTRAINT IF EXISTS stock_listing_status_chk")
    op.execute("ALTER TABLE stock DROP COLUMN IF EXISTS listing_status")
