"""stock UNIQUE(cik) → UNIQUE(cik, ticker) — 다중 클래스주 보존

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-18

S5-b 라이브 검증 버그 수정(code-bug): cik 은 **발행사(issuer)** 식별자라 다중 클래스주가 한 cik 를
공유한다(GOOG·GOOGL→1652044, BRK-A·BRK-B→1067983 실측). 부분 UNIQUE(cik) 는 `ON CONFLICT(cik)`
upsert 에서 클래스주를 1행으로 collapse 시켜 GOOGL·BRK-B 등이 마스터에서 소실됐다(~883행 손실 실측).
→ UNIQUE 를 **(cik, ticker)** 로 변경(보안=ticker 단위·발행사=cik). 미해소(cik NULL)는 여전히 부분
인덱스 밖(다수 공존). R1 의 'cik UNIQUE' → '(cik,ticker) UNIQUE' 정정.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS stock_cik_uq")
    op.execute(
        "CREATE UNIQUE INDEX stock_cik_ticker_uq ON stock (cik, ticker) WHERE cik IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS stock_cik_ticker_uq")
    op.execute("CREATE UNIQUE INDEX stock_cik_uq ON stock (cik) WHERE cik IS NOT NULL")
